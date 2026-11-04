"""A new talk from a folder, or several files (pedido de 04/11/2026; Fase 1, item 9): PDFs, notes, .tex/.bib and
images all go to context/, each PDF is extracted into a folder of its own, and the first request lists them."""
import json
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import open_studio, wait_until
from tests.e2e.test_projects import make_pdf
from tests.helpers.kit_copy import remove_tree

FOLDER_MESSAGE = "#scenario:import-folder Materiais:\n{files}"


@pytest.fixture(scope="module")
def folders():
    root = Path(tempfile.mkdtemp(prefix="deck-studio-projects-"))
    yield root
    remove_tree(root)


@pytest.fixture(scope="module")
def studio_args(folders):
    config = folders / "config.json"
    config.write_text(json.dumps({"importFolderMessage": FOLDER_MESSAGE, "projectsFolder": str(folders)}),
                      encoding="utf-8")
    return ["--config", config]


PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de0000000c4944415408d763f8ffff3f"
                    "0005fe02fea7d6a6580000000049454e44ae426082")
FILES = {"mock/notas.md": b"# Notas\n\nO piloto mediu 42 proteinas.\n", "mock/roteiro.md": b"# Roteiro\n",
         "mock/artigo-a.pdf": make_pdf(), "mock/artigo-b.pdf": make_pdf(), "mock/img/foto.png": PNG,
         "mock/programa.exe": b"MZ", "../fora.md": b"x"}


def _multipart(files):
    boundary = "----deckstudiotest"
    body = b""
    for name, data in files.items():
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"files\"; filename=\"{name}\"\r\n"
                 f"Content-Type: application/octet-stream\r\n\r\n").encode() + data + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return {"data": body, "headers_extra": f"multipart/form-data; boundary={boundary}"}


def post(api, studio, files, **query):
    extra = _multipart(files)
    return api.post(f"{studio.base}/api/projects/import-files?{urlencode(query)}",
                    headers={**studio.headers, "content-type": extra["headers_extra"]}, data=extra["data"],
                    timeout=120_000)


def first_message(url):
    """The first chat's messages of the project's studio, once its agent answered."""
    u = urlsplit(url)
    base, token = f"{u.scheme}://{u.netloc}", parse_qs(u.query)["t"][0]

    def answered():
        req = urllib.request.Request(f"{base}/api/chats", headers={"x-studio-token": token})
        chats = json.loads(urllib.request.urlopen(req, timeout=10).read())
        msgs = chats[0]["messages"] if chats else []
        return msgs if any(m["kind"] == "text" for m in msgs) else None
    return wait_until(answered, 60, "the project's first answer")


def test_a_folder_becomes_a_project_with_every_source_in_context(studio, api, folders):
    r = post(api, studio, FILES, name="Pasta de Teste", format="html", language="pt")
    assert r.status == 201, r.text()
    data = r.json()
    assert data["skipped"] == ["../fora.md", "mock/programa.exe"]
    root = Path(data["project"]["path"])
    context = root / "context"
    for rel in ["mock/notas.md", "mock/roteiro.md", "mock/artigo-a.pdf", "mock/artigo-b.pdf", "mock/img/foto.png"]:
        assert (context / rel).read_bytes() == FILES[rel], rel
    assert not (context / "mock" / "programa.exe").exists() and not (root / "fora.md").exists()
    assert not (folders / "fora.md").exists()
    # each PDF in a folder of its own, as the single-PDF import extracts it
    for out in ("artigo-a", "artigo-b"):
        assert "42 proteínas" in (context / out / "texto.md").read_text(encoding="utf-8"), out
        assert json.loads((context / out / "info.json").read_text(encoding="utf-8"))["pages"] == 1
    assert json.loads((root / "studio.json").read_text(encoding="utf-8"))["format"] == "html"

    msgs = first_message(data["url"])
    request = next(m["text"] for m in msgs if m["kind"] == "user")
    assert "`context/mock/artigo-a.pdf`: o texto em `context/artigo-a/texto.md`" in request
    assert "`context/mock/notas.md` (texto)" in request and "`context/mock/img/foto.png` (imagem)" in request
    assert "Ficaram de fora (tipo não aceito): ../fora.md, mock/programa.exe." in request


def test_a_broken_pdf_or_an_empty_folder_leaves_nothing_behind(studio, api, folders):
    before = sorted(p.name for p in folders.iterdir())
    r = post(api, studio, {"pasta/x.pdf": b"isto nao e um pdf", "pasta/a.md": b"# A\n"}, name="Quebrado",
             format="html", language="pt")
    assert r.status == 400 and "não é um PDF" in r.json()["message"]
    r = post(api, studio, {"pasta/programa.exe": b"MZ"}, name="Vazio", format="html", language="pt")
    assert r.status == 400 and r.json()["error"] == "no-files"
    r = post(api, studio, {"a.md": b"x"}, name="Sem formato", format="pptx", language="pt")
    assert r.status == 400 and r.json()["error"] == "bad-format"
    assert sorted(p.name for p in folders.iterdir()) == before


def test_the_panel_takes_a_folder_and_names_the_project_after_it(studio, page, tmp_path):
    folder = tmp_path / "Exoplanetas na feira"
    (folder / "img").mkdir(parents=True)
    (folder / "notas.md").write_text("# Notas\n", encoding="utf-8")
    (folder / "artigo.pdf").write_bytes(make_pdf())
    (folder / "img" / "foto.png").write_bytes(PNG)
    open_studio(page, studio)
    page.get_by_role("button", name="Projetos").click()
    page.locator("input[type=file][webkitdirectory]").set_input_files(folder)
    form = page.get_by_role("form", name="Nova apresentação a partir de um PDF ou de uma pasta")
    expect(form).to_contain_text("3 arquivos (1 PDF)")
    expect(form.get_by_label("Nome")).to_have_value("Exoplanetas na feira")
