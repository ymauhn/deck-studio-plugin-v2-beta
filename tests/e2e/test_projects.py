"""Importing a PDF (docs/IMPORT.md "User flow", "CLI and processes", "Registry", "HTTP"): the studio makes a project
folder from the template, extracts the PDF into it, registers it in <home>/projects.json and opens the project in a
studio of its own, a child process, whose chat starts with the request to build the talk.

The module's studio is the home (run_studio's data dir). Its --config reaches the children too: the fake agent's
importMessage starts with #scenario:import-<format>, and new projects go in a temp folder, never in the profile."""
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urlsplit

import pymupdf
import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import deck_of, open_studio, run_studio, wait_until
from deck_studio.core import plataforma
from tests.helpers.kit_copy import REAL_KIT, remove_tree

MESSAGE = "#scenario:import-{format} Crie a apresentação a partir de `{pdf}` em {language}. Texto: `{text}`. " \
          "Figuras: `{figures}`."


def make_pdf():
    """A title, two headings, a sentence with a number and an embedded PNG (docs/IMPORT.md "Tests")."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Proteínas em Rede", fontsize=24)
    page.insert_text((72, 120), "Introdução", fontsize=16)
    page.insert_text((72, 145), "O modelo anota 42 proteínas com uma rede de interação.", fontsize=11)
    page.insert_text((72, 190), "Resultados", fontsize=16)
    page.insert_text((72, 215), "A rede melhora o Fmax em todas as ontologias avaliadas.", fontsize=11)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 160), False)
    pix.clear_with(120)
    pix.set_rect(pymupdf.IRect(0, 0, 100, 160), (30, 90, 160))  # two colours: a single-colour image is dropped
    page.insert_image(pymupdf.Rect(72, 240, 272, 400), stream=pix.tobytes("png"))
    page.insert_text((72, 420), "Figura 1: Uma imagem de teste.", fontsize=10)
    return doc.tobytes()


PDF = make_pdf()


def make_scanned_pdf():
    """A page that is only an image, as a scanner makes it: no text to extract."""
    doc = pymupdf.open()
    page = doc.new_page()
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 300, 400), False)
    pix.clear_with(200)
    page.insert_image(page.rect, stream=pix.tobytes("png"))
    return doc.tobytes()


@pytest.fixture(scope="module")
def folders():
    """Where this module's projects go."""
    root = Path(tempfile.mkdtemp(prefix="deck-studio-projects-"))
    yield root
    remove_tree(root)


@pytest.fixture(scope="module")
def studio_args(folders):
    config = folders / "config.json"
    config.write_text(json.dumps({"importMessage": MESSAGE, "projectsFolder": str(folders)}), encoding="utf-8")
    return ["--config", config]


def post_import(api, studio, body=PDF, file_name="artigo.pdf", **query):
    """POST /api/projects/import as the panel sends it: the raw PDF, its name in x-file-name, the rest in the query."""
    return api.post(f"{studio.base}/api/projects/import?{urlencode(query)}", data=body, timeout=120_000,
                    headers={**studio.headers, "content-type": "application/pdf", "x-file-name": quote(file_name)})


def open_project(api, studio, path):
    return api.post(f"{studio.base}/api/projects/open", data={"path": str(path)}, headers=studio.headers,
                    timeout=90_000)


def launch_url(made):
    """The import's URL opens the new studio on the chat of its first request (#chat=<id>); without that, it is the
    studio's launch URL."""
    url, chat = made["url"].split("#chat=")
    assert re.fullmatch(r"[\w-]+", chat)
    return url


def child_of(made):
    """The base URL and the auth headers of the project's own studio, from the import's answer."""
    u = urlsplit(made["url"])
    return f"{u.scheme}://{u.netloc}", {"x-studio-token": parse_qs(u.query)["t"][0]}


def imported(studio, folder, name, playwright, **query):
    api = playwright.request.new_context()
    try:
        r = post_import(api, studio, name=name, folder=str(folder), **{"format": "html", "language": "pt", **query})
        assert r.status == 201, r.text()
        return folder, r.json()
    finally:
        api.dispose()


@pytest.fixture(scope="module")
def html_project(studio, folders, playwright):
    """One HTML import, made once for the tests that look at its parts."""
    return imported(studio, folders / "Proteínas em Rede", "Proteínas em Rede", playwright)


@pytest.fixture(scope="module")
def same_name(studio, folders, html_project, playwright):
    """A second project named as the first, made after it."""
    return imported(studio, folders / "Outra cópia" / "Proteínas em Rede", "Proteínas em Rede", playwright)


# ---------- an HTML import ----------

def test_an_import_makes_the_project_folder_from_the_template_with_its_studio_json_and_the_pdf(html_project):
    folder, _ = html_project
    for rel in ["CLAUDE.md", ".claude/skills/criar-apresentacao/SKILL.md", "deck/build.py", "deck/src/shell.html",
                "deck/src/slides/00-title.html", "beamer/apresentacao/apresentacao.tex", "tools/overleaf_zip.py"]:
        assert (folder / rel).is_file(), rel
    assert json.loads((folder / "studio.json").read_text(encoding="utf-8")) == {
        "title": "Proteínas em Rede", "format": "html", "language": "pt", "startMode": "html",
        "beamerStart": "beamer/apresentacao/apresentacao.tex"}
    assert (folder / "context" / "artigo.pdf").read_bytes() == PDF
    claude = (folder / "CLAUDE.md").read_text(encoding="utf-8")
    assert "{{" not in claude
    assert "`context/artigo.pdf`" in claude
    assert "`context/proteinas-em-rede/`" in claude


def test_the_pdf_is_extracted_into_context_slug_as_text_figures_and_info(html_project):
    out = html_project[0] / "context" / "proteinas-em-rede"
    text = (out / "texto.md").read_text(encoding="utf-8")
    assert text.startswith("# Proteínas em Rede\n\n## Página 1")
    for part in ["### Introdução", "### Resultados", "O modelo anota 42 proteínas"]:
        assert part in text
    assert sorted(p.name for p in (out / "figuras").iterdir()) == ["p001-1.png"]
    info = json.loads((out / "info.json").read_text(encoding="utf-8"))
    assert (info["title"], info["pages"]) == ("Proteínas em Rede", 1)
    assert info["figures"] == [{"file": "figuras/p001-1.png", "page": 1, "width": 200, "height": 160,
                                "caption": "Figura 1: Uma imagem de teste."}]


def test_the_import_answers_the_url_of_the_projects_own_studio_named_after_it(html_project, page):
    _, made = html_project
    assert made["url"].startswith("http://127.0.0.1:")
    page.goto(made["url"])
    expect(page).to_have_title("Proteínas em Rede · Deck Studio")
    expect(page.get_by_role("banner")).to_contain_text("Proteínas em Rede")


def test_its_chat_starts_with_the_request_to_build_the_talk_and_the_deck_shows_the_slide_the_agent_wrote(
        html_project, page):
    _, made = html_project
    page.goto(made["url"])
    log = page.get_by_role("log", name="Conversa")
    expect(log.get_by_role("article", name="Você")).to_have_text(
        "#scenario:import-html Crie a apresentação a partir de `context/artigo.pdf` em português. "
        "Texto: `context/proteinas-em-rede/texto.md`. Figuras: `context/proteinas-em-rede/figuras`.")
    expect(log.get_by_role("article", name="Claude")).to_have_text("Criei o primeiro slide a partir do PDF.")
    expect(deck_of(page).locator("section#s02")).to_contain_text("O modelo anota 42 proteínas com uma rede de interação.")


# ---------- the registry and the list ----------

def test_the_registry_keeps_each_imported_project_and_never_the_default_kit(studio, html_project):
    folder, _ = html_project
    registry = json.loads((studio.data / "projects.json").read_text(encoding="utf-8"))
    project = next(p for p in registry if p["path"] == str(folder))
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d", project.pop("created"))
    assert project == {"name": "Proteínas em Rede", "slug": "proteinas-em-rede", "path": str(folder), "format": "html",
                       "language": "pt"}
    assert all(p["path"] != str(REAL_KIT) for p in registry)


def test_a_second_project_with_the_same_name_gets_the_next_slug(same_name):
    folder, made = same_name
    assert made["project"]["slug"] == "proteinas-em-rede-2"
    assert (folder / "context" / "proteinas-em-rede-2" / "texto.md").is_file()


def test_api_projects_lists_the_default_kit_then_the_projects_newest_first_with_their_running_studios(
        studio, html_project, same_name, api):
    r = api.get(f"{studio.base}/api/projects", headers=studio.headers).json()
    assert r["current"] == {"name": "NEXUS-GO", "path": str(studio.kit)}
    builtin = r["projects"][0]
    assert {k: builtin[k] for k in ("name", "path", "format", "builtin")} == {
        "name": "NEXUS-GO (kit da defesa)", "path": str(REAL_KIT), "format": "html", "builtin": True}
    paths = [p["path"] for p in r["projects"]]
    assert paths.index(str(same_name[0])) < paths.index(str(html_project[0]))
    project = r["projects"][paths.index(str(html_project[0]))]
    assert {k: project[k] for k in ("name", "slug", "format", "language", "running", "url")} == {
        "name": "Proteínas em Rede", "slug": "proteinas-em-rede", "format": "html", "language": "pt", "running": True,
        "url": launch_url(html_project[1])}


# ---------- opening a project again ----------

def test_opening_the_project_again_reuses_its_running_studio_on_the_chat_of_its_request(studio, html_project, api):
    """Its chat, not a new empty one beside the generation: the URL names the chat whose turn runs, else the one used
    last, as the import's URL does."""
    folder, made = html_project
    r = open_project(api, studio, folder)
    assert (r.status, r.json()) == (200, {"url": made["url"]})


def test_another_studio_on_the_same_home_opens_that_running_studio_through_its_lock(studio, html_project, api):
    folder, made = html_project
    with run_studio("--home", studio.data, kit=studio.kit) as other:
        listed = api.get(f"{other.base}/api/projects", headers=other.headers).json()["projects"]
        assert next(p for p in listed if p["path"] == str(folder))["url"] == launch_url(made)
        r = open_project(api, other, folder)
        assert (r.status, r.json()) == (200, {"url": made["url"]})


def test_two_studios_on_one_home_importing_at_once_keep_both_projects_apart(studio, studio_args, folders):
    """Every studio of a home has the import form. Two imports at once, of one name, get a slug and a data dir each,
    and both stay in the registry."""
    def made(s, folder):
        query = urlencode({"name": "Simultâneo", "format": "html", "language": "pt", "folder": str(folder)})
        request = urllib.request.Request(f"{s.base}/api/projects/import?{query}", PDF, {
            **s.headers, "content-type": "application/pdf", "x-file-name": "artigo.pdf"})
        with urllib.request.urlopen(request, timeout=120) as r:
            return json.loads(r.read())

    with run_studio("--home", studio.data, *studio_args, kit=studio.kit) as other:
        with ThreadPoolExecutor(2) as pool:
            a, b = pool.map(made, [studio, other], [folders / "Simultâneo A", folders / "Simultâneo B"])
    assert sorted([a["project"]["slug"], b["project"]["slug"]]) == ["simultaneo", "simultaneo-2"]
    registry = json.loads((studio.data / "projects.json").read_text(encoding="utf-8"))
    assert sorted((p["slug"], p["path"]) for p in registry if p["name"] == "Simultâneo") == sorted(
        (m["project"]["slug"], m["project"]["path"]) for m in (a, b))
    assert launch_url(a) != launch_url(b)


def test_opening_a_project_whose_studio_is_still_starting_waits_for_its_url(studio, studio_args, folders, api):
    """Another studio of the home may be starting the project's studio, which holds its data dir's lock with no URL
    yet: Abrir waits for that URL instead of starting a second studio there, which could only fail."""
    folder = folders / "Iniciando"
    with run_studio("--home", studio.data, *studio_args, kit=studio.kit) as other:
        made = post_import(api, other, name="Iniciando", format="html", language="pt", folder=str(folder))
        assert made.status == 201, made.text()
    # its studio ended with `other`; the test now holds its lock as a studio that starts does (__main__.lock_data_dir)
    lock = studio.data / "projects" / made.json()["project"]["slug"] / "studio.lock"
    url = "http://127.0.0.1:9/?t=starting"
    fd = os.open(lock, os.O_RDWR | plataforma.O_BINARY)
    ready = threading.Timer(6, lambda: lock.write_text(url, encoding="utf-8"))
    try:
        os.lseek(fd, 1 << 30, os.SEEK_SET)
        plataforma.lock_byte(fd)
        os.ftruncate(fd, 0)
        ready.start()
        r = open_project(api, studio, folder)
        assert (r.status, r.json()) == (200, {"url": url})
    finally:
        ready.cancel()
        os.close(fd)


def test_a_project_whose_folder_is_gone_is_marked_and_can_be_taken_off_the_list(studio, studio_args, folders, api,
                                                                                 page):
    """Remover da lista changes the list only: the folder (here, already deleted) and the studio's data stay as
    they are."""
    folder = folders / "Apagado"
    with run_studio("--home", studio.data, *studio_args, kit=studio.kit) as other:  # its studio ends with `other`
        made = post_import(api, other, name="Apagado", format="html", language="pt", folder=str(folder))
        assert made.status == 201, made.text()
    remove_tree(folder)
    open_studio(page, studio)
    panel = panel_of(page)
    row = listed(panel).filter(has_text="Apagado")
    expect(row).to_contain_text("pasta não encontrada")
    row.get_by_role("button", name="Remover Apagado da lista").click()
    page.get_by_role("dialog").get_by_role("button", name="Confirmar").click()
    expect(row).to_have_count(0)
    assert str(folder) not in [p["path"] for p in json.loads((studio.data / "projects.json").read_text(encoding="utf-8"))]
    assert (studio.data / "projects" / made.json()["project"]["slug"]).is_dir()
    r = api.post(f"{studio.base}/api/projects/remove", data={"path": str(folder)}, headers=studio.headers)
    assert (r.status, r.json()) == (404, {"error": "not-found", "message": "Este projeto não está na lista de projetos."})


def test_opening_a_folder_that_is_not_a_project_is_refused(studio, folders, api):
    r = open_project(api, studio, folders)
    assert (r.status, r.json()) == (404, {"error": "not-found", "message": "Este projeto não está na lista de projetos."})


# ---------- a Beamer import ----------

def test_a_beamer_import_opens_its_studio_in_beamer_mode_with_the_template_compiled(studio, folders, api, page):
    folder = folders / "Lecture on Networks"
    r = post_import(api, studio, name="Lecture on Networks", format="beamer", language="en", folder=str(folder))
    assert r.status == 201, r.text()
    tex = folder / "beamer" / "apresentacao" / "apresentacao.tex"
    assert "\\usepackage[english]{babel}" in tex.read_text(encoding="utf-8")
    page.goto(r.json()["url"])
    expect(page).to_have_title("Lecture on Networks · Deck Studio")
    expect(page.get_by_role("group", name="Modo").get_by_role("button", name="Beamer")).to_have_attribute(
        "aria-pressed", "true")
    expect(page.locator(".beamer-bar [role=status]")).to_have_text(re.compile(r"^Compilado em \d+,\d s$"),
                                                                    timeout=90_000)
    expect(page.get_by_role("region", name="Beamer").get_by_role("img", name=re.compile(r"^Página 1 de \d+$"))
           ).to_be_visible()
    # its first request ran the import-beamer scenario, which edits the deck's .tex
    expect(page.get_by_role("log", name="Conversa").get_by_role("article", name="Claude")).to_have_text(
        "Preenchi a autoria do Beamer a partir do PDF.")
    assert "\\author{Ana Souza}" in tex.read_text(encoding="utf-8")
    # one "Projetos" on screen, the top bar's: the Beamer view's own button goes back to its list of decks
    expect(page.get_by_role("button", name="Projetos", exact=True)).to_have_count(1)
    # the Files pane shows the deck's folder as the project's own, not as read-only
    base, headers = child_of(r.json())
    roots = api.get(f"{base}/api/files", headers=headers).json()
    assert [(x["path"], x["readOnly"]) for x in roots if x["kind"] == "beamer"] == [("beamer/apresentacao", False)]


# ---------- refusals ----------

INSIDE = "Esta pasta fica dentro de um projeto ou do kit. Escolha uma fora deles."
NOT_EMPTY = "Esta pasta já existe e tem arquivos. Escolha uma pasta nova ou vazia."
LOCAL = "Escolha uma pasta num disco deste computador, como C:\\Users\\voce\\Deck Studio\\Projeto."
LONG = "O caminho da pasta passa de 150 caracteres, longo demais para o Windows. Escolha uma pasta ou um nome mais curto."
TEX = "O caminho da pasta não pode ter os caracteres % ~ $ { }: o LaTeX não compila nele."
REFUSALS = {  # what is wrong: (query changes, body, file name, error, message)
    "a name with a slash": ({"name": "Capítulo 1/2"}, PDF, "artigo.pdf",
                            "bad-name", 'Dê um nome ao projeto, sem os caracteres / \\ : * ? " < > |.'),
    "no name": ({"name": "  "}, PDF, "artigo.pdf",
                "bad-name", 'Dê um nome ao projeto, sem os caracteres / \\ : * ? " < > |.'),
    "an unknown format": ({"format": "pptx"}, PDF, "artigo.pdf", "bad-format", "Escolha o formato: HTML ou Beamer."),
    "an unknown language": ({"language": "fr"}, PDF, "artigo.pdf",
                            "bad-language", "Escolha o idioma dos slides: português ou inglês."),
    "a file that is not a .pdf": ({}, PDF, "artigo.docx", "bad-file", "Escolha um arquivo .pdf."),
    "a body that is not a PDF": ({}, b"PK\x03\x04 um docx", "artigo.pdf", "not-pdf", "Este arquivo não é um PDF."),
    "a PDF that does not open": ({}, b"%PDF-1.7\nnada aqui", "artigo.pdf", "bad-pdf", "Não foi possível ler este PDF."),
    "a relative folder": ({"folder": "Projetos\\Recusado"}, PDF, "artigo.pdf", "bad-folder",
                          "Informe a pasta pelo caminho completo, como C:\\Users\\voce\\Deck Studio\\Projeto."),
    "a folder with files": ({"folder": "{used}"}, PDF, "artigo.pdf", "folder-not-empty", NOT_EMPTY),
    "a folder in the kit": ({"folder": "{kit}\\deck\\novo"}, PDF, "artigo.pdf", "folder-inside", INSIDE),
    "a folder in a project": ({"folder": "{project}\\novo"}, PDF, "artigo.pdf", "folder-inside", INSIDE),
    # other spellings of a folder inside: Windows drops a trailing space, and resolve() keeps \\?\ then
    "a folder in the kit spelled with a space": ({"folder": "{kit} \\novo"}, PDF, "artigo.pdf", "folder-inside", INSIDE),
    "a folder in a project spelled as a device path": ({"folder": "\\\\?\\{project}\\novo"}, PDF, "artigo.pdf",
                                                       "folder-inside", INSIDE),
    "a folder in the kit through a network share": ({"folder": "{kit_share}\\novo"}, PDF, "artigo.pdf",
                                                    "bad-folder", LOCAL),
    "a folder too long for Windows": ({"folder": "{folders}\\" + "x" * 150}, PDF, "artigo.pdf", "long-folder", LONG),
    "a folder LaTeX cannot compile in": ({"folder": "{folders}\\Custo de 30%"}, PDF, "artigo.pdf", "bad-folder", TEX),
}


@pytest.mark.parametrize("wrong", REFUSALS)
def test_a_bad_import_is_refused_with_400_in_portuguese_and_leaves_nothing_behind(wrong, studio, folders, html_project,
                                                                                  api):
    changes, body, file_name, error, message = REFUSALS[wrong]
    used = folders / "Usada"
    used.mkdir(exist_ok=True)
    (used / "notas.txt").write_text("minhas notas", encoding="utf-8")
    folder = folders / "Recusado"
    query = {"name": "Recusado", "format": "html", "language": "pt", "folder": str(folder), **changes}
    kit_share = f"\\\\localhost\\{studio.kit.drive[0]}${str(studio.kit)[2:]}"  # \\localhost\C$\...: the kit, shared
    query["folder"] = query["folder"].format(used=used, kit=studio.kit, project=html_project[0], kit_share=kit_share,
                                             folders=folders)
    registry = studio.data / "projects.json"
    before = registry.read_bytes()
    r = post_import(api, studio, body, file_name, **query)
    assert (r.status, r.json()) == (400, {"error": error, "message": message})
    assert not folder.exists()
    assert query["folder"] == str(used) or not Path(query["folder"]).exists()
    for inside in [studio.kit / "deck" / "novo", studio.kit / "novo", html_project[0] / "novo"]:
        assert not inside.exists()
    assert [p.name for p in used.iterdir()] == ["notas.txt"]
    assert registry.read_bytes() == before


def test_an_import_in_the_default_folder_leaves_out_what_latex_refuses_and_never_reuses_a_folder(studio, folders,
                                                                                                api):
    """The default folder is <projects folder>\\<Nome> without % ~ $ { }. A second import of one name, sent with no
    folder or with that default one (as the panel sends it), goes to "<Nome> (2)" instead of being refused."""
    first = post_import(api, studio, name="Custo de 30% {final}", format="html", language="pt")
    assert first.status == 201, first.text()
    again = post_import(api, studio, name="Custo de 30% {final}", format="beamer", language="pt",
                        folder=str(folders / "Custo de 30 final"))
    assert again.status == 201, again.text()
    assert [first.json()["project"]["path"], again.json()["project"]["path"]] == [
        str(folders / "Custo de 30 final"), str(folders / "Custo de 30 final (2)")]


SCANNED = ("Este PDF quase não tem texto selecionável: parece escaneado. O agente vai ler as páginas como imagens, o que "
           "demora mais.")


def test_a_pdf_without_text_is_imported_with_a_warning_and_its_request_says_to_read_the_pages(studio, folders, api,
                                                                                               page):
    r = post_import(api, studio, make_scanned_pdf(), "digitalizado.pdf", name="Digitalizado", format="html",
                    language="pt", folder=str(folders / "Digitalizado"))
    assert r.status == 201, r.text()
    assert r.json()["warning"] == SCANNED
    page.goto(r.json()["url"])
    expect(page.get_by_role("log", name="Conversa").get_by_role("article", name="Você")).to_contain_text(
        "O PDF quase não tem texto selecionável (parece escaneado): leia as páginas de `context/digitalizado.pdf` "
        "com a ferramenta Read.")


def make_abstract_pdf():
    """A thesis excerpt that starts at its abstract: its first heading is "Resumo", then "Abstract"."""
    doc = pymupdf.open()
    for heading, text in (("Resumo", "Este trabalho anota 42 proteínas com uma rede de interação."),
                          ("Abstract", "This work annotates 42 proteins with an interaction network.")):
        page = doc.new_page()
        page.insert_text((72, 100), heading, fontsize=24)
        page.insert_text((72, 140), text, fontsize=11)
    return doc.tobytes()


def test_a_pdf_that_starts_at_its_abstract_is_not_titled_after_the_abstracts_heading(studio, folders, api):
    """The title guess skips the front matter's headings (Resumo, Abstract, Sumário...): a first page with nothing
    else in its largest type leaves the PDF's file name as the title."""
    folder = folders / "Trecho"
    r = post_import(api, studio, make_abstract_pdf(), "Trecho da tese.pdf", name="Trecho", format="html",
                    language="pt", folder=str(folder))
    assert r.status == 201, r.text()
    out = folder / "context" / "trecho"
    assert json.loads((out / "info.json").read_text(encoding="utf-8"))["title"] == "Trecho da tese"
    assert (out / "texto.md").read_text(encoding="utf-8").startswith("# Trecho da tese\n\n## Página 1\n\n### Resumo")


def test_a_name_whose_slug_windows_reserves_gets_the_next_one(studio, folders, api):
    """"Nül" is a plain name, but its slug "nul" is a device on Windows: no folder can have that name."""
    r = post_import(api, studio, name="Nül", format="html", language="pt", folder=str(folders / "Nül"))
    assert r.status == 201, r.text()
    assert r.json()["project"]["slug"] == "nul-2"
    assert (folders / "Nül" / "context" / "nul-2" / "texto.md").is_file()


def test_an_import_whose_registry_cannot_be_written_answers_in_portuguese_and_leaves_nothing_behind(
        studio, folders, html_project, api):
    """A reader holds projects.json for the whole import (Python's open() does not share delete): the save retries,
    then gives up. The folder and the slug's data dir go."""
    folder = folders / "Sem registro"
    with open(studio.data / "projects.json", encoding="utf-8"):
        r = post_import(api, studio, name="Sem registro", format="html", language="pt", folder=str(folder))
    assert (r.status, r.json()) == (500, {"error": "no-register",
                                          "message": "O projeto não entrou na lista de projetos. Tente de novo."})
    assert not folder.exists()
    assert not (studio.data / "projects" / "sem-registro").exists()
    assert not list(studio.data.glob("projects.*.tmp"))


def test_a_pdf_over_100_mb_is_refused(studio, folders):
    """Sent with urllib: 100 MB does not go through the browser driver."""
    query = urlencode({"name": "Grande", "format": "html", "language": "pt", "folder": str(folders / "Grande")})
    request = urllib.request.Request(f"{studio.base}/api/projects/import?{query}", PDF.ljust(100 * 1024 * 1024 + 1),
                                     {**studio.headers, "content-type": "application/pdf", "x-file-name": "grande.pdf"})
    with pytest.raises(urllib.error.HTTPError) as refused:
        urllib.request.urlopen(request, timeout=60)
    assert refused.value.code == 400
    assert json.loads(refused.value.read()) == {"error": "too-large", "message": "O PDF passa de 100 MB."}
    assert not (folders / "Grande").exists()


# ---------- the Projetos panel ----------

def panel_of(page):
    """The Projetos panel, opened from the top bar."""
    page.get_by_role("banner").get_by_role("button", name="Projetos").click()
    return page.get_by_role("dialog", name="Projetos")


def listed(panel):
    return panel.get_by_role("list", name="Projetos").get_by_role("listitem")


def new_form(panel):
    return panel.get_by_role("form", name="Nova apresentação a partir de um PDF")


def test_the_projetos_panel_lists_this_studio_the_default_kit_and_the_imported_projects_with_abrir(studio_page,
                                                                                                   html_project):
    """This studio's kit is a copy, so the default kit is listed apart, second; on the default kit itself, the first
    row is the default kit, as this studio's."""
    panel = panel_of(studio_page)
    here, builtin = listed(panel).nth(0), listed(panel).nth(1)
    expect(here).to_contain_text("NEXUS-GO")
    expect(here).to_contain_text("Neste studio")
    expect(here.get_by_role("button", name="Abrir")).to_have_count(0)
    expect(builtin).to_contain_text("NEXUS-GO (kit da defesa)")
    expect(builtin.get_by_title(str(REAL_KIT))).to_have_text("…\\Desktop\\nexusgo_deck_kit")
    expect(listed(panel).filter(has_text="Proteínas em Rede").get_by_role("button", name="Abrir")).to_be_visible()


def test_abrir_opens_the_running_project_studio_in_a_new_tab_on_its_chat(studio_page, html_project):
    panel = panel_of(studio_page)
    with studio_page.expect_popup() as popup:
        listed(panel).filter(has_text="Proteínas em Rede").get_by_role("button", name="Abrir").click()
    tab = popup.value
    expect(tab).to_have_title("Proteínas em Rede · Deck Studio", timeout=30_000)
    assert tab.url.startswith(launch_url(html_project[1]).split("?")[0])
    expect(tab.get_by_role("log", name="Conversa").get_by_role("article", name="Você")).to_contain_text(
        "#scenario:import-html")
    expect(tab.get_by_role("tablist", name="Chats").get_by_role("tab")).to_have_count(1)


def test_when_the_browser_keeps_the_tab_shut_the_panel_links_to_the_project(studio_page, html_project):
    page = studio_page
    page.evaluate("() => { window.open = () => null; }")  # as a popup blocker answers
    panel = panel_of(page)
    listed(panel).filter(has_text="Proteínas em Rede").get_by_role("button", name="Abrir").click()
    expect(panel.get_by_role("status").get_by_role("link", name="Abrir o projeto")).to_have_attribute(
        "href", html_project[1]["url"])


def test_the_panel_creates_a_project_from_a_pdf_and_opens_it_in_a_new_tab_on_its_first_request(studio_page, folders):
    page = studio_page
    form = new_form(panel_of(page))
    form.get_by_label("PDF").set_input_files({"name": "Relatório anual.pdf", "mimeType": "application/pdf",
                                              "buffer": PDF})
    expect(form.get_by_label("Nome")).to_have_value("Relatório anual")
    expect(form.get_by_role("textbox", name="Pasta")).to_have_value(str(folders / "Relatório anual"))
    expect(form.get_by_label("HTML (deck web)")).to_be_checked()
    expect(form.get_by_label("Português")).to_be_checked()
    # what the PDF cannot say (the time, the audience, the event) goes to the agent with the request
    form.get_by_label("Instruções para o agente").fill("Palestra de 20 minutos para a banca, em 5/11.")
    with page.expect_popup() as popup:
        form.get_by_role("button", name="Criar apresentação").click()
    tab = popup.value
    expect(tab).to_have_title("Relatório anual · Deck Studio", timeout=60_000)
    request = tab.get_by_role("log", name="Conversa").get_by_role("article", name="Você")
    expect(request).to_contain_text(
        "#scenario:import-html Crie a apresentação a partir de `context/Relatório anual.pdf` em português.")
    expect(request).to_contain_text("Instruções do autor: Palestra de 20 minutos para a banca, em 5/11.")
    expect(form.get_by_role("link", name="Abrir o projeto")).to_have_attribute("href", re.compile(r"^http://127\.0\.0\.1:"))
    expect(listed(page.get_by_role("dialog", name="Projetos")).filter(has_text="Relatório anual")).to_be_visible()
    assert (folders / "Relatório anual" / "context" / "relatorio-anual" / "texto.md").is_file()


def test_the_status_of_an_import_never_pushes_criar_apresentacao_out_of_the_panel(studio_page):
    """The panel keeps its size: when the status shows, the button and its hint stay in view, whole."""
    page = studio_page
    form = new_form(panel_of(page))
    form.get_by_label("PDF").set_input_files({"name": "Visível.pdf", "mimeType": "application/pdf", "buffer": PDF})
    with page.expect_popup():
        form.get_by_role("button", name="Criar apresentação").click()
    expect(form.get_by_role("status")).to_contain_text("Pronto: o projeto abriu em outra aba.", timeout=60_000)
    expect(form.get_by_role("button", name="Criar apresentação")).to_be_in_viewport(ratio=1)
    expect(form.get_by_text("O agente começa logo em seguida")).to_be_in_viewport(ratio=1)
    expect(form.get_by_role("status")).to_be_in_viewport(ratio=1)


def test_the_panel_shows_why_the_studio_refused_an_import_and_closes_the_blank_tab(studio_page, folders):
    page = studio_page
    used = folders / "Ocupada"
    used.mkdir(exist_ok=True)
    (used / "notas.txt").write_text("minhas notas", encoding="utf-8")
    form = new_form(panel_of(page))
    form.get_by_label("PDF").set_input_files({"name": "artigo.pdf", "mimeType": "application/pdf", "buffer": PDF})
    form.get_by_role("textbox", name="Pasta").fill(str(used))
    form.get_by_label("Beamer (LaTeX)").check()
    with page.expect_popup() as popup:
        form.get_by_role("button", name="Criar apresentação").click()
    popup.value.wait_for_event("close")
    expect(form.get_by_role("alert")).to_have_text(NOT_EMPTY)
    expect(form.get_by_role("button", name="Criar apresentação")).to_be_enabled()


LONG_PDF = ("Beyond_Learnable_Graphs__Fixed_Multi_Hop_PPI_Diffusion_of_Sequence_Embeddings_for_Robust_Protein_Function_"
            "Prediction.pdf")


def test_a_pdf_with_a_long_file_name_makes_a_project_whose_paths_fit_windows(studio_page, folders):
    """Paths stop at 260 characters on this PC (LongPathsEnabled is 0). The default Nome is the file name with spaces
    for underscores, cut before a word at 60 characters; the slug stops at 40 and the saved PDF's name at 60."""
    page = studio_page
    form = new_form(panel_of(page))
    form.get_by_label("PDF").set_input_files({"name": LONG_PDF, "mimeType": "application/pdf", "buffer": PDF})
    name = "Beyond Learnable Graphs Fixed Multi Hop PPI Diffusion of"
    expect(form.get_by_label("Nome")).to_have_value(name)
    expect(form.get_by_role("textbox", name="Pasta")).to_have_value(str(folders / name))
    with page.expect_popup() as popup:
        form.get_by_role("button", name="Criar apresentação").click()
    expect(popup.value).to_have_title(f"{name} · Deck Studio", timeout=60_000)
    context = folders / name / "context"
    assert (context / "Beyond_Learnable_Graphs__Fixed_Multi_Hop_PPI_Diffusion_of.pdf").read_bytes() == PDF
    assert (context / "beyond-learnable-graphs-fixed-multi-hop" / "figuras" / "p001-1.png").is_file()


def test_the_default_folder_leaves_out_the_characters_latex_refuses_in_a_path(studio_page, folders):
    form = new_form(panel_of(studio_page))
    form.get_by_label("PDF").set_input_files({"name": "Custo de 30% {final}.pdf", "mimeType": "application/pdf",
                                              "buffer": PDF})
    expect(form.get_by_label("Nome")).to_have_value("Custo de 30% {final}")
    expect(form.get_by_role("textbox", name="Pasta")).to_have_value(str(folders / "Custo de 30 final"))


def test_the_panel_refuses_a_name_windows_cannot_use_before_it_opens_a_tab(studio_page):
    page = studio_page
    popups = []
    page.on("popup", lambda tab: popups.append(tab))
    form = new_form(panel_of(page))
    form.get_by_label("PDF").set_input_files({"name": "artigo.pdf", "mimeType": "application/pdf", "buffer": PDF})
    form.get_by_label("Nome").fill("Parte 1: Introdução")
    form.get_by_role("button", name="Criar apresentação").click()
    expect(form.get_by_role("alert")).to_have_text('Dê um nome ao projeto, sem os caracteres / \\ : * ? " < > |.')
    assert popups == []


def test_the_panel_takes_only_a_pdf(studio_page):
    form = new_form(panel_of(studio_page))
    form.get_by_label("PDF").set_input_files({"name": "notas.docx", "mimeType": "application/octet-stream",
                                              "buffer": b"PK\x03\x04"})
    expect(form.get_by_role("alert")).to_have_text("Escolha um arquivo .pdf.")
    expect(form.get_by_label("Nome")).to_have_value("")


def test_without_an_import_message_in_the_config_the_first_request_is_the_default_one(folders, api, page):
    config = folders / "default-message.json"
    config.write_text(json.dumps({"projectsFolder": str(folders)}), encoding="utf-8")
    with run_studio("--config", config) as parent:
        r = post_import(api, parent, name="Padrão", format="beamer", language="en", folder=str(folders / "Padrão"))
        assert r.status == 201, r.text()
        page.goto(r.json()["url"])
        expect(page.get_by_role("log", name="Conversa").get_by_role("article", name="Você")).to_have_text(
            "Crie a apresentação a partir do PDF `context/artigo.pdf`, no formato Beamer, com os slides em inglês. O texto "
            "extraído está em `context/padrao/texto.md` e as figuras em `context/padrao/figuras`. Siga a skill "
            "criar-apresentacao e o CLAUDE.md do projeto.")


# ---------- processes ----------

def answers(url):
    """Whether a server answers at url, whatever its answer."""
    try:
        with urllib.request.urlopen(url, timeout=2):
            return True
    except urllib.error.HTTPError:
        return True
    except OSError:
        return False


def test_a_project_studio_ends_with_the_studio_that_started_it_and_abrir_starts_a_new_one(studio_args, folders, api):
    folder = folders / "Efêmero"
    with run_studio(*studio_args) as parent:
        r = post_import(api, parent, name="Efêmero", format="html", language="pt", folder=str(folder))
        assert r.status == 201, r.text()
        child = launch_url(r.json())
        assert answers(child)
        parent.proc.kill()  # it alone, not its tree
        parent.proc.wait()
        wait_until(lambda: not answers(child), timeout=20, message="the project's studio to end")
        with run_studio("--home", parent.data, kit=parent.kit) as again:  # the same home, after a restart
            r = open_project(api, again, folder)
            assert r.status == 200, r.text()
            assert r.json()["url"] != child
            assert answers(r.json()["url"])


# ---------- the extraction alone, as projects.extract runs it (docs/IMPORT.md "PDF extraction") ----------

APP = Path(__file__).resolve().parents[2]
PEAK = """import ctypes, sys
from deck_studio.pdf_import import extract
extract(sys.argv[1], sys.argv[2])
if sys.platform != "win32":
    import resource
    print(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)  # KB on Linux
    sys.exit()
from ctypes import wintypes
class Counters(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD), ("peak", ctypes.c_size_t)] + [
        (f"other{i}", ctypes.c_size_t) for i in range(7)]
kernel = ctypes.windll.kernel32
kernel.GetCurrentProcess.restype = wintypes.HANDLE
kernel.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
counters = Counters(cb=ctypes.sizeof(Counters))
assert kernel.K32GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
print(counters.peak)"""


@pytest.fixture
def scratch():
    root = Path(tempfile.mkdtemp(prefix="deck-studio-extract-"))
    yield root
    remove_tree(root)


def masked_pdf(side):
    """A 200 x 200 image whose soft mask declares side x side pixels: a small file that decodes to side² bytes."""
    doc = pymupdf.open()
    page = doc.new_page()
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 200), True)
    pix.clear_with(120)
    page.insert_image(pymupdf.Rect(72, 72, 272, 272), pixmap=pix)
    smask = page.get_images()[0][1]
    z = zlib.compressobj(9)
    doc.update_stream(smask, b"".join(z.compress(bytes(side)) for _ in range(side)) + z.flush(), compress=False)
    for key, value in {"Width": side, "Height": side, "BitsPerComponent": 8, "Filter": "/FlateDecode",
                       "DecodeParms": "null"}.items():
        doc.xref_set_key(smask, key, str(value))
    return doc.tobytes()


def test_an_images_soft_mask_counts_in_the_pixel_caps(scratch):
    """The caps hold the PDF's images to 40 MP each: a soft mask declared bigger is never decoded either."""
    peaks = []
    for side in (200, 12_000):
        (scratch / f"{side}.pdf").write_bytes(masked_pdf(side))
        r = subprocess.run([sys.executable, "-c", PEAK, str(scratch / f"{side}.pdf"), str(scratch / str(side))],
                           cwd=APP, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        peaks.append(int(r.stdout) >> 20)
    assert peaks[1] < peaks[0] + 50, f"peak memory: {peaks[0]} MB with a 200² mask, {peaks[1]} MB with a 12000² one"


def extracted(scratch, pdf):
    """info.json's object from `python -m deck_studio.pdf_import`, the extraction's process."""
    (scratch / "in.pdf").write_bytes(pdf)
    r = subprocess.run([sys.executable, "-m", "deck_studio.pdf_import", str(scratch / "in.pdf"), str(scratch / "out")],
                       cwd=APP, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads((scratch / "out" / "info.json").read_text(encoding="utf-8"))


BODY = "O texto do artigo continua aqui com uma frase longa de várias palavras."


def drawn_pdf():
    """Two charts drawn as vectors, as LaTeX and ABNT place their captions, and a single-colour image."""
    doc = pymupdf.open()
    page = doc.new_page()  # A4: 595 x 842 pt
    page.insert_text((72, 100), BODY, fontsize=11)
    for i, top in enumerate((200, 150, 170)):  # red bars on an axis, with their labels under it
        page.draw_rect(pymupdf.Rect(120 + 90 * i, top, 180 + 90 * i, 260), color=None, fill=(1, 0, 0))
        page.insert_text((140 + 90 * i, 275), ("BP", "CC", "MF")[i], fontsize=9)
    page.draw_line((110, 260), (400, 260))
    page.insert_text((72, 300), "Figure 1: Fmax por ontologia no conjunto de teste.", fontsize=10)
    page.insert_text((72, 330), BODY, fontsize=11)
    black = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 300, 200), False)
    black.clear_with(0)
    page.insert_image(pymupdf.Rect(72, 500, 372, 700), stream=black.tobytes("png"))
    page = doc.new_page()  # ABNT: the caption above the figure, its source under it
    page.insert_text((72, 100), BODY, fontsize=11)
    page.insert_text((72, 140), "Figura 2 - Rede de interação entre proteínas.", fontsize=10)
    page.draw_line((200, 200), (350, 240))
    for center in ((200, 200), (350, 240)):
        page.draw_circle(center, 30, color=(0, 0, 1), fill=(0, 0, 1))
    page.insert_text((72, 310), "Fonte: o autor.", fontsize=9)
    page.insert_text((72, 360), BODY, fontsize=11)
    return doc.tobytes()


def test_a_figure_drawn_as_vectors_is_rendered_with_its_caption_and_a_single_colour_image_is_dropped(scratch):
    info = extracted(scratch, drawn_pdf())
    assert [(f["file"], f["page"], f["caption"]) for f in info["figures"]] == [
        ("figuras/p001-fig-1.png", 1, "Figure 1: Fmax por ontologia no conjunto de teste."),
        ("figuras/p002-fig-2.png", 2, "Figura 2 - Rede de interação entre proteínas.")]
    assert sorted(p.name for p in (scratch / "out" / "figuras").iterdir()) == ["p001-fig-1.png", "p002-fig-2.png"]
    # each one is its chart at 200 dpi (pt x 200 / 72), labels included, without the text around it
    for f, colour, (w, h), (above, below) in [(info["figures"][0], b"\xff\x00\x00", (290, 117), (103, 292)),
                                              (info["figures"][1], b"\x00\x00\xff", (210, 100), (143, 349))]:
        png = pymupdf.Pixmap(str(scratch / "out" / f["file"]))
        assert (png.width, png.height) == (f["width"], f["height"])
        assert w * 200 / 72 <= png.width <= 595 * 200 / 72 and h * 200 / 72 <= png.height < (below - above) * 200 / 72
        assert png.samples.count(colour) > 10_000


def text_pdf():
    """A table set cell by cell, as LaTeX sets one, a word split across two lines, a Portuguese word that keeps its
    hyphen, and a long reference list."""
    doc = pymupdf.open()
    page = doc.new_page()
    for y, row in ((72, "T BP CC MF"), (86, "0 53.36 65.21 73.18"), (100, "1 55.21 66.11 73.11")):
        for x, cell in zip((72, 130, 190, 250), row.split()):
            page.insert_text((x, y), cell, fontsize=10)
    page.insert_text((72, 140), "Each protein gets an anno-\ntation from the network, and each annotation is\n"
                                "checked. O modelo adotou-\nse em 2020.", fontsize=10)
    references = (f"[{i}] Autor {i}, A. Um título de artigo sobre redes de proteínas. Revista {i}, 2020."
                  for i in range(1, 50))
    page.insert_text((72, 220), "\n".join(references), fontsize=6)
    return doc.tobytes()


def test_texto_md_keeps_a_tables_rows_and_lines_the_read_tool_reads_whole(scratch):
    extracted(scratch, text_pdf())
    text = (scratch / "out" / "texto.md").read_text(encoding="utf-8")
    assert "T BP CC MF\n" in text and "\n0 53.36 65.21 73.18\n1 55.21 66.11 73.11\n" in text  # a row per line
    assert "Each protein gets an annotation from the network" in text  # "annotation" is in the PDF unbroken too
    assert "O modelo adotou-se em 2020." in text
    assert max(len(line) for line in text.splitlines()) < 2000  # Claude Code's Read cuts longer lines
    assert all(f"[{i}] Autor {i}, A. Um título" in text for i in range(1, 50))
