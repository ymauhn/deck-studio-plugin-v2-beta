"""Seam 1: the Files pane (SPEC stories 6 and 45-49): its folders, part jumps, @references and uploads into context/."""
import json
import re
import urllib.error
import urllib.request
from urllib.parse import quote

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import ROOT, deck_of, go_slide, open_studio, slide_and_step, wait_until

DOT = ROOT / "tests" / "fixtures" / "beamer" / "figures" / "dot.png"
MB = 1024 * 1024


@pytest.fixture(scope="module")
def user_skills(tmp_path_factory):
    """Stands in for ~/.claude/skills, so the tests never list the real one."""
    folder = tmp_path_factory.mktemp("home") / "skills"
    (folder / "demo").mkdir(parents=True)
    (folder / "demo" / "SKILL.md").write_text("---\nname: demo\n---\n", encoding="utf-8")
    return folder


@pytest.fixture(scope="module")
def studio_args(tmp_path_factory, user_skills):
    config = tmp_path_factory.mktemp("cfg") / "config.json"
    config.write_text(json.dumps({"readDirs": [str(user_skills)]}), encoding="utf-8")
    return ["--config", config]


def files_pane(page):
    return page.get_by_role("region", name="Arquivos")


def composer(page):
    return page.get_by_role("textbox", name="Mensagem")


def conversation(page):
    return page.get_by_role("log", name="Conversa")


def list_dir(studio, api, folder):
    return api.get(f"{studio.base}/api/files", params={"dir": folder}, headers=studio.headers)


def upload(studio, api, name, data):
    return api.post(f"{studio.base}/api/files/upload", data=data,
                    headers={**studio.headers, "x-file-name": quote(name, safe="")})


def upload_raw(studio, name, data):
    """POST straight from the standard library: big bodies stay out of the Playwright driver."""
    request = urllib.request.Request(f"{studio.base}/api/files/upload", data=data, method="POST",
                                     headers={**studio.headers, "x-file-name": quote(name, safe="")})
    try:
        with urllib.request.urlopen(request) as res:
            return res.status, json.load(res)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def drop(page, *files):
    """Drop (name, data) files on the Files pane, the way a drag from the desktop does.
    `data` is bytes, or a size: that many zero bytes, made in the page."""
    transfer = page.evaluate_handle("""(files) => {
        const transfer = new DataTransfer();
        for (const [name, data] of files) transfer.items.add(new File([new Uint8Array(data)], name));
        return transfer;
    }""", [[name, data if isinstance(data, int) else list(data)] for name, data in files])
    for kind in ["dragenter", "dragover", "drop"]:
        files_pane(page).dispatch_event(kind, {"dataTransfer": transfer})


def test_the_files_pane_lists_the_slide_sources_the_images_the_context_folder_and_the_project_skills(studio_page):
    pane = files_pane(studio_page)
    expect(pane.get_by_role("list", name="deck/src/slides").get_by_role("listitem")).to_have_text([
        "00-opening.html", "01-motivation.html", "02-background.html", "03-data.html", "04-method.html",
        "05-results.html", "06-conclusions.html", "07-backup.html"])
    for folder in ["deck/src/img/", "context/", ".claude/skills/"]:
        expect(pane.get_by_text(folder, exact=True)).to_be_visible()


def test_api_files_lists_a_folder_inside_the_roots_and_refuses_every_path_outside_them(studio, api):
    slides = list_dir(studio, api, "deck/src/slides")
    assert slides.status == 200
    assert {"name": "03-data.html", "path": "deck/src/slides/03-data.html", "dir": False} in slides.json()
    assert list_dir(studio, api, ".claude/skills").json() == []  # a root that does not exist yet is empty

    for path in ["deck/src/slides/nope", "deck/src/slides/03-data.html"]:
        res = list_dir(studio, api, path)
        assert (res.status, res.json()["error"]) == (404, "not-found"), path

    outside = ["data", "deck", "deck/build", "deck/src/slidesx", "C:/Windows", "context/..", "context/../data",
               "deck/src/slides/../../build", r"deck/src/slides/..\..\build", "deck/src/slides/C:/Windows",
               "deck/src/slides//03-data.html", "context/nul"]
    for path in outside:
        res = list_dir(studio, api, path)
        assert (res.status, res.json()["error"]) == (403, "outside"), path

    assert api.get(f"{studio.base}/api/files").status == 401  # no token, no listing


def test_clicking_a_part_file_jumps_the_deck_to_its_first_slide_and_alt_click_adds_its_reference(studio_page):
    page = studio_page
    assert slide_and_step(page) == (1, 0)
    files_pane(page).get_by_role("button", name="04-method.html").click()
    wait_until(lambda: slide_and_step(page) == (18, 0), message="slide 18, the first of 04-method.html")
    expect(deck_of(page).locator("#s18")).to_be_visible()
    # a plain click only navigates, so the deck keeps the arrow keys; it does not type a reference
    expect(composer(page)).to_have_value("")
    # Alt+click still drops the reference for a message
    files_pane(page).get_by_role("button", name="04-method.html").click(modifiers=["Alt"])
    expect(composer(page)).to_have_value("@deck/src/slides/04-method.html ")


def test_the_part_file_of_the_slide_on_screen_is_marked_current(studio_page):
    page = studio_page
    pane = files_pane(page)
    expect(pane.get_by_role("button", name="00-opening.html")).to_have_attribute("aria-current", "true")
    go_slide(page, 18)
    expect(pane.get_by_role("button", name="04-method.html")).to_have_attribute("aria-current", "true")
    expect(pane.locator("[aria-current]")).to_have_count(1)
    page.evaluate("() => studio.deck.reload()")  # a rebuilt deck is a new page in the frame
    go_slide(page, 13)
    expect(pane.get_by_role("button", name="03-data.html")).to_have_attribute("aria-current", "true")


def test_a_file_dropped_on_the_pane_is_saved_in_context_with_progress_a_toast_and_a_reference_on_click(
        studio, studio_page):
    page = studio_page
    name, data = "notas do orientador – revisão.md", b"# Notas\r\nrevisar o slide 13\n"
    held = []
    page.route("**/api/files/upload", lambda route: held.append(route))  # the upload waits until the test lets it go
    drop(page, (name, data))
    sending = files_pane(page).get_by_role("status")
    expect(sending).to_contain_text(f"Enviando {name}")
    wait_until(lambda: page.wait_for_timeout(50) or held, message="the upload request")
    held[0].continue_()

    expect(page.get_by_role("status").filter(has_text=f"Salvo em context/{name}")).to_be_visible()
    expect(sending).to_be_hidden()
    assert (studio.kit / "context" / name).read_bytes() == data
    files_pane(page).get_by_role("list", name="context").get_by_role("button", name=name).click()
    expect(composer(page)).to_have_value(f"@context/{name} ")


def test_an_upload_never_overwrites_a_file_it_takes_the_next_free_numbered_name(studio, api):
    sent = [upload(studio, api, name, data) for name, data in [
        ("artigo.pdf", b"one"), ("artigo.pdf", b"two"), ("ARTIGO.PDF", b"three")]]
    assert [(r.status, r.json()) for r in sent] == [
        (201, {"name": "artigo.pdf", "path": "context/artigo.pdf"}),
        (201, {"name": "artigo (2).pdf", "path": "context/artigo (2).pdf"}),
        (201, {"name": "ARTIGO (3).PDF", "path": "context/ARTIGO (3).PDF"}),  # Windows names ignore case
    ]
    context = studio.kit / "context"
    assert [(context / n).read_bytes() for n in ["artigo.pdf", "artigo (2).pdf", "ARTIGO (3).PDF"]] == [
        b"one", b"two", b"three"]


def test_an_upload_over_50_mb_or_named_with_anything_but_a_plain_file_name_is_refused_and_writes_nothing(
        studio, api):
    context = studio.kit / "context"
    assert upload_raw(studio, "limite.bin", bytes(50 * MB)) == (201, {"name": "limite.bin", "path": "context/limite.bin"})
    before = sorted(p.name for p in context.iterdir())

    status, body = upload_raw(studio, "grande.bin", bytes(50 * MB + 1))
    assert (status, body["error"]) == (413, "too-large")
    for name in ["", ".", "..", "../fora.md", r"..\fora.md", "sub/x.md", "C:x.md", "x.md:stream", "nul", "con.txt",
                 "x.md.", "x.md ", "x\tmd"]:
        res = upload(studio, api, name, b"x")
        assert (res.status, res.json()["error"]) == (400, "bad-name"), name
    for header in ["%FF.md", "a/b.md", None]:  # not UTF-8, not encoded, missing
        headers = {**studio.headers, **({"x-file-name": header} if header else {})}
        res = api.post(f"{studio.base}/api/files/upload", data=b"x", headers=headers)
        assert (res.status, res.json()["error"]) == (400, "bad-name"), header

    assert sorted(p.name for p in context.iterdir()) == before
    assert not (studio.kit / "fora.md").exists()


def test_a_dropped_file_over_50_mb_is_not_sent_and_a_toast_says_why(studio, studio_page):
    page = studio_page
    sent = []
    page.on("request", lambda r: sent.append(r.url) if "/api/files/upload" in r.url else None)
    drop(page, ("grande.pdf", 50 * MB + 1))
    expect(page.get_by_role("alert").filter(has_text="grande.pdf passa de 50 MB")).to_be_visible()
    assert sent == []
    assert not (studio.kit / "context" / "grande.pdf").exists()


def test_an_image_in_context_shows_a_thumbnail_and_por_no_slide_asks_the_agent_to_place_it_with_add_image(
        studio, studio_page, api):
    page = studio_page
    drop(page, ("figura nova.png", DOT.read_bytes()))
    item = files_pane(page).get_by_role("list", name="context").get_by_role("listitem").filter(has_text="figura nova.png")
    wait_until(lambda: item.locator("img").evaluate("(img) => img.complete && img.naturalWidth"), message="the thumbnail")

    go_slide(page, 13)
    item.get_by_role("button", name="Pôr no slide").click()
    chat = conversation(page)
    expect(chat.get_by_role("article", name="Você").last).to_have_text(
        "Ponha a imagem @context/figura nova.png no slide 13. Use a ferramenta add_image.")
    expect(chat.get_by_role("article", name="Claude").last).to_have_text("ok")  # the fake agent, with no scenario

    def image(path):
        return api.get(f"{studio.base}/api/files/image", params={"path": path}, headers=studio.headers)

    shown = image("context/figura nova.png")
    assert (shown.status, shown.headers["content-type"], shown.body()) == (200, "image/png", DOT.read_bytes())
    assert shown.headers["content-security-policy"] == "sandbox"  # an SVG opened by itself runs no script
    assert image("deck/src/slides/03-data.html").status == 404  # images only
    assert image("deck/build/fonts.css").status == 403


def test_the_user_skills_and_the_handwritten_beamer_decks_are_listed_read_only(studio, studio_page, api):
    page = studio_page
    talk = studio.kit / "beamer" / "palestra" / "palestra.tex"
    talk.parent.mkdir(parents=True)
    talk.write_text("\\documentclass{beamer}\n\\begin{document}\n\\end{document}\n", encoding="utf-8")
    roots = api.get(f"{studio.base}/api/files", headers=studio.headers).json()
    assert [(r["kind"], r["readOnly"]) for r in roots] == [
        ("slides", False), ("images", False), ("context", False), ("skills", False), ("user-skills", True),
        ("beamer", True)]
    assert re.fullmatch(r"~/.+/skills", roots[4]["path"])  # a folder in the home folder is shown from ~
    assert roots[5]["path"] == "beamer/palestra"

    open_studio(page, studio)
    pane = files_pane(page)
    read_only = pane.locator("summary").filter(has_text="só leitura")
    expect(read_only).to_have_text([re.compile(r"^~/.+/skills/ só leitura$"), "beamer/palestra/ só leitura"])
    read_only.last.click()
    expect(pane.get_by_role("list", name="beamer/palestra").get_by_role("listitem")).to_have_text(["palestra.tex"])
    read_only.first.click()
    pane.locator("summary").filter(has_text="demo/").click()
    pane.get_by_role("button", name="SKILL.md").click()
    expect(composer(page)).to_have_value(re.compile(r"^@~/.+/skills/demo/SKILL\.md $"))


def test_files_made_during_a_chat_turn_show_up_in_the_pane_when_the_turn_ends(studio, studio_page):
    page = studio_page
    context = files_pane(page).get_by_role("list", name="context")
    expect(context).to_be_visible()
    (studio.kit / "context").mkdir(exist_ok=True)
    (studio.kit / "context" / "resumo do agente.md").write_text("# Resumo\n", encoding="utf-8")  # as an agent's Write
    expect(context.get_by_role("button", name="resumo do agente.md")).to_have_count(0)

    composer(page).fill("#scenario:hello")
    composer(page).press("Enter")
    expect(context.get_by_role("button", name="resumo do agente.md")).to_be_visible()
