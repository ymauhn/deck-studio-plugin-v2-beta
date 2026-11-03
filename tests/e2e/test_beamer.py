"""Beamer mode ([beamer-ui]): the HTML | Beamer switch, the project list, the page view, clicks that select TeX
lines or HTML boxes, the frame editor and the recompiles.

The kit copy holds a copy of beamer/academico, the fixture deck as beamer/palestra (CRLF, like the kit's own .tex
files) and the generated deck's existing outputs (PDF, .nav, sources, layout.json), which are never compiled.
The beamer job is a harmless command that only touches the generated PDF."""
import json
import re
import shutil
import sys
from urllib.parse import urlsplit

import pymupdf
import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import ROOT, deck_of, open_studio, run_studio, slide_and_step
from tests.helpers.kit_copy import make_kit_copy, remove_kit_copy

FIXTURE = ROOT / "tests" / "fixtures" / "beamer"
GENERATED = ["beamer/nexus-go-defense.tex", "beamer/nexus-go-defense.pdf", "beamer/nexus-go-defense.nav",
             "beamer/slides.tex", "beamer/build/layout.json"]
TALK = "beamer/palestra/talk.tex"
CONFIG = {
    "allowWrite": ["deck/src/**", "context/**", ".claude/skills/**", "beamer/academico/**", "beamer/palestra/**"],
    "jobs": {"beamer": [[sys.executable, "-c", "import os; os.utime('beamer/nexus-go-defense.pdf'); print('regenerado')"]]},
}


@pytest.fixture(scope="module")
def studio_args(tmp_path_factory):
    config = tmp_path_factory.mktemp("beamer") / "config.json"
    config.write_text(json.dumps(CONFIG), encoding="utf-8")
    return ["--config", config]


@pytest.fixture(scope="module")
def studio(studio_args):
    kit = make_kit_copy(extra=["beamer/academico", *GENERATED])
    try:
        shutil.copytree(FIXTURE, kit / "beamer" / "palestra")
        (kit / TALK).write_bytes((FIXTURE / "talk.tex").read_bytes().replace(b"\n", b"\r\n"))
        with run_studio(*studio_args, kit=kit) as s:
            yield s
    finally:
        remove_kit_copy(kit)


def mode_button(page, name):
    return page.get_by_role("group", name="Modo").get_by_role("button", name=name)


def projects(page):
    return page.get_by_role("list", name="Projetos Beamer")


def cards(page):
    return page.get_by_role("log", name="Conversa").get_by_role("article", name="Alterações")


def open_project(page, name):
    mode_button(page, "Beamer").click()
    projects(page).get_by_role("button", name=re.compile(rf"^{re.escape(name)} ")).click()


def bar_status(page):
    """The compile status in the deck bar."""
    return page.locator(".beamer-bar [role=status]")


def compiled(page):
    expect(bar_status(page)).to_have_text(re.compile(r"^Compilado em \d+,\d s$"), timeout=90_000)


def page_image(page):
    return page.get_by_role("region", name="Beamer").get_by_role("img")


def loaded(image):
    image.page.wait_for_function("img => img.complete && img.naturalWidth > 0", arg=image.element_handle())


def talk_pdf(studio):
    """The fixture deck as the studio compiled it, to find where its words are."""
    return studio.data / "beamer" / "palestra-talk" / "talk.pdf"


def click_word(page, pdf, pno, word, nth=0):
    """Click the nth occurrence of a word on the page image of page pno (1-based) of pdf."""
    with pymupdf.open(pdf) as d:
        p = d[pno - 1]
        hits = [w for w in p.get_text("words") if re.sub(r"^\W+|\W+$", "", w[4]) == word]
        fx, fy = (hits[nth][0] + hits[nth][2]) / 2 / p.rect.width, (hits[nth][1] + hits[nth][3]) / 2 / p.rect.height
    box = page_image(page).bounding_box()
    page.mouse.click(box["x"] + fx * box["width"], box["y"] + fy * box["height"])


def chips(page):
    return page.get_by_role("list", name="Seleção").get_by_role("listitem")


def source_pane(page):
    return page.get_by_role("region", name="Fonte LaTeX")


def thumbnails(page):
    return page.get_by_role("list", name="Páginas").get_by_role("button")


def test_the_beamer_switch_lists_the_projects_and_html_brings_the_deck_back(studio_page):
    page = studio_page
    expect(mode_button(page, "HTML")).to_have_attribute("aria-pressed", "true")
    mode_button(page, "Beamer").click()
    assert page.evaluate("() => studio.mode.get()") == "beamer"
    expect(mode_button(page, "Beamer")).to_have_attribute("aria-pressed", "true")
    expect(projects(page).get_by_role("listitem")).to_have_text([
        re.compile(r"^nexus-go-academic\.tex\s*beamer/academico · escrito à mão$"),
        re.compile(r"^nexus-go-defense\.tex\s*beamer · gerado do HTML$"),
        re.compile(r"^talk\.tex\s*beamer/palestra · escrito à mão$"),
    ])
    expect(page.get_by_role("button", name="Selecionar (S)")).to_be_hidden()  # the HTML deck's tools

    mode_button(page, "HTML").click()
    expect(projects(page)).to_be_hidden()
    expect(page.get_by_role("button", name="Selecionar (S)")).to_be_visible()
    assert page.evaluate("() => studio.mode.get()") == "html"


def test_opening_a_handwritten_deck_compiles_it_into_the_app_data_and_shows_pages_thumbnails_and_keys(studio, studio_page):
    page = studio_page
    open_project(page, "talk.tex")
    expect(bar_status(page)).to_have_text("Compilando…")
    compiled(page)
    expect(page_image(page)).to_have_accessible_name("Página 1 de 8")
    expect(thumbnails(page)).to_have_count(8)
    expect(thumbnails(page).first).to_have_attribute("aria-current", "true")
    for key, n in [("ArrowRight", 2), ("PageDown", 3), ("PageUp", 2), ("ArrowLeft", 1), ("ArrowLeft", 1)]:
        page.keyboard.press(key)
        expect(page_image(page)).to_have_accessible_name(f"Página {n} de 8")
    thumbnails(page).nth(6).click()
    expect(page_image(page)).to_have_accessible_name("Página 7 de 8")
    expect(thumbnails(page).nth(6)).to_have_attribute("aria-current", "true")
    loaded(page_image(page))

    assert (studio.data / "beamer" / "palestra-talk" / "talk.pdf").is_file()
    assert sorted(p.name for p in (studio.kit / "beamer" / "palestra").iterdir()) == ["figures", "talk.tex"]


HARBOR = r"""\begin{frame}{Harbor Water}
  \begin{itemize}[<+->]
    \item Lanterns glow over quiet water
    \item Fishermen mend their nets
    \item Gulls circle the old pier
  \end{itemize}
\end{frame}"""


def test_a_click_on_a_page_selects_its_tex_line_as_a_chip_and_opens_the_frame_source(studio, studio_page):
    page = studio_page
    open_project(page, "talk.tex")
    compiled(page)
    thumbnails(page).nth(3).click()
    expect(page_image(page)).to_have_accessible_name("Página 4 de 8")

    click_word(page, talk_pdf(studio), 4, "Gulls")
    expect(chips(page)).to_have_text(["Harbor Water talk.tex:18"])
    [selected] = page.evaluate("() => studio.selection.get()")
    assert {k: selected[k] for k in ("kind", "file", "frame", "line", "page", "title")} == {
        "kind": "tex", "file": TALK, "frame": {"start": 14, "end": 20}, "line": 18, "page": 4, "title": "Harbor Water"}
    assert "Gulls" in selected["text"]
    expect(source_pane(page)).to_contain_text("talk.tex, linhas 14 a 20")
    expect(source_pane(page).get_by_role("textbox", name="LaTeX do frame")).to_have_value(HARBOR)
    expect(source_pane(page).get_by_role("button", name="Salvar")).to_be_disabled()  # nothing to save yet

    page.keyboard.down("Shift")  # Shift+click adds, as in the HTML deck
    click_word(page, talk_pdf(studio), 4, "Lanterns")
    page.keyboard.up("Shift")
    expect(chips(page)).to_have_text(["Harbor Water talk.tex:18", "Harbor Water talk.tex:16"])

    mode_button(page, "HTML").click()
    expect(source_pane(page)).to_be_hidden()
    expect(chips(page)).to_have_count(2)  # the selection stays for the chat


def test_a_chat_message_carries_the_tex_selection(studio, studio_page):
    page = studio_page
    open_project(page, "talk.tex")
    compiled(page)
    thumbnails(page).nth(6).click()
    click_word(page, talk_pdf(studio), 7, "Thanks")
    expect(chips(page)).to_have_text(["Closing Remarks talk.tex:35"])

    composer = page.get_by_role("textbox", name="Mensagem")
    composer.fill("#scenario:selection")
    composer.press("Enter")
    conversation = page.get_by_role("log", name="Conversa")
    expect(conversation.get_by_role("article", name="Claude").last).to_have_text("Seleção: tex beamer/palestra/talk.tex:35")
    expect(conversation.get_by_role("article", name="Você").last.get_by_role("listitem")).to_have_text(
        ["Closing Remarks talk.tex:35"])
    expect(chips(page)).to_have_count(0)  # sent: the composer starts over


def track_compiles(page):
    """From now on, window.compiles gets [scope, state, page image name, status] at each `beamer` event, as shown."""
    page.evaluate("""() => { window.compiles = []; studio.on('beamer', (e) => window.compiles.push([e.scope, e.state,
        document.querySelector('.beamer-page').alt, document.querySelector('.beamer-status').textContent])); }""")


def compiles(page, n):
    page.wait_for_function("n => window.compiles.length >= n", arg=n, timeout=90_000)
    return page.evaluate("() => window.compiles")


DONE = re.compile(r"^Compilado em \d+,\d s$")


def test_saving_the_frame_is_an_undoable_turn_shown_first_as_a_frame_preview_then_in_the_whole_deck(studio, studio_page):
    page = studio_page
    open_project(page, "talk.tex")
    compiled(page)
    thumbnails(page).nth(5).click()
    click_word(page, talk_pdf(studio), 6, "Thunder")
    box = source_pane(page).get_by_role("textbox", name="LaTeX do frame")
    expect(box).to_have_value(re.compile(r"^\\begin\{frame\}\{Mountain Weather\}\n"))
    before = (studio.kit / TALK).read_bytes()
    n = cards(page).count()  # the cards of this module's earlier saves come back with the page

    box.fill(box.input_value().replace("Thunder rolls across", "Thunder rumbles over"))
    track_compiles(page)
    page.evaluate("""() => { window.reloads = 0; studio.deck.frame.addEventListener('load', () => window.reloads++);
        window.builds = 0; studio.on('build', () => window.builds++); }""")
    box.press("Control+s")
    card = cards(page).nth(n)
    expect(card).to_contain_text("Frame editado em talk.tex:22")
    expect(card).to_contain_text(TALK)
    # the frame (pages 5 and 6 of the deck) alone first, on the same page, then the whole deck
    [frame_run, frame_ok, full_run, full_ok] = compiles(page, 4)
    assert frame_run[:3] == ["frame", "running", "Página 6 de 8"]
    assert frame_ok[:3] == ["frame", "ok", "Página 2 de 2"]
    assert full_run == ["full", "running", "Página 2 de 2", "Prévia do frame · compilando o deck…"]
    assert full_ok[:3] == ["full", "ok", "Página 6 de 8"] and DONE.match(full_ok[3])
    assert (studio.kit / TALK).read_bytes() == before.replace(b"Thunder rolls across", b"Thunder rumbles over")
    expect(source_pane(page).get_by_role("button", name="Salvar")).to_be_disabled()
    # a .tex feeds no HTML build: the HTML deck under the view is neither built nor reloaded, the typing stays put
    assert page.evaluate("() => [window.builds, window.reloads]") == [0, 0]
    expect(box).to_be_focused()


def compile_errors(page):
    return page.get_by_role("region", name="Beamer").get_by_role("alert")


def test_compile_errors_show_with_their_file_and_line_until_the_frame_compiles_again(studio, studio_page):
    page = studio_page
    open_project(page, "talk.tex")
    compiled(page)
    thumbnails(page).nth(1).click()
    click_word(page, talk_pdf(studio), 2, "Lanterns")
    box = source_pane(page).get_by_role("textbox", name="LaTeX do frame")
    save = source_pane(page).get_by_role("button", name="Salvar")
    expect(box).to_have_value(re.compile("Fishermen mend their nets"))

    track_compiles(page)
    box.fill(box.input_value().replace("their nets", "their BROKEN nets").replace("BROKEN", chr(92) + "nosuchmacro"))
    save.click()
    assert [c[:2] for c in compiles(page, 4)] == [["frame", "running"], ["frame", "error"], ["full", "running"], ["full", "error"]]
    # TeX reads a frame body whole: it reports the error on the frame's \end{frame} line
    expect(compile_errors(page)).to_have_text("talk.tex:20 Undefined control sequence.")
    expect(bar_status(page)).to_have_text("A compilação falhou.")

    box.fill(box.input_value().replace(chr(92) + "nosuchmacro ", ""))
    save.click()
    assert [c[:2] for c in compiles(page, 8)[4:]] == [["frame", "running"], ["frame", "ok"], ["full", "running"], ["full", "ok"]]
    expect(compile_errors(page)).to_have_count(0)
    compiled(page)


def test_an_agent_edit_to_the_tex_and_its_undo_recompile_the_deck_and_the_frame_source_follows(studio, studio_page):
    page = studio_page
    open_project(page, "talk.tex")
    compiled(page)
    thumbnails(page).nth(6).click()
    click_word(page, talk_pdf(studio), 7, "Thanks")
    box = source_pane(page).get_by_role("textbox", name="LaTeX do frame")
    expect(box).to_have_value(re.compile("Thanks for listening."))
    before = (studio.kit / TALK).read_bytes()
    n = cards(page).count()  # the cards of this module's earlier saves come back with the page

    track_compiles(page)
    composer = page.get_by_role("textbox", name="Mensagem")
    composer.fill("#scenario:beamer-edit")
    composer.press("Enter")
    assert [c[:2] for c in compiles(page, 2)] == [["full", "running"], ["full", "ok"]]
    expect(box).to_have_value(re.compile("Thank you for listening."))  # nothing was typed in it: it follows the file
    assert "Thank you for listening." in (studio.kit / TALK).read_text(encoding="utf-8")

    card = cards(page).nth(n)
    expect(card).to_contain_text(TALK)
    card.get_by_role("button", name="Desfazer").click()
    expect(card).to_contain_text("Desfeito.")
    assert [c[:2] for c in compiles(page, 4)[2:]] == [["full", "running"], ["full", "ok"]]
    expect(box).to_have_value(re.compile("Thanks for listening."))
    assert (studio.kit / TALK).read_bytes() == before


def test_a_click_on_the_generated_deck_selects_the_html_box_at_the_same_slide_step_and_point(studio, studio_page):
    page = studio_page
    open_project(page, "nexus-go-defense.tex")
    expect(page_image(page)).to_have_accessible_name("Página 1 de 321")
    expect(bar_status(page)).to_have_text("PDF gerado do HTML")
    for _ in range(5):
        page.keyboard.press("ArrowRight")
    expect(page_image(page)).to_have_accessible_name("Página 6 de 321")
    loaded(page_image(page))

    click_word(page, studio.kit / "beamer" / "nexus-go-defense.pdf", 6, "Sequencing")
    expect(chips(page)).to_have_text(["s03 li 01-motivation.html:6"])
    assert slide_and_step(page) == (3, 3)  # page 6 is the last step of s03
    [selected] = page.evaluate("() => studio.selection.get()")
    assert (selected["slideId"], selected["step"], selected["kind"]) == ("s03", 3, "text")
    assert selected["text"].startswith("Sequencing is fast")
    expect(source_pane(page)).to_be_hidden()  # the HTML is the source: edits go there, through the chat
    assert not (studio.data / "beamer" / "nexus-go-defense").exists()  # never compiled

    mode_button(page, "HTML").click()
    expect(deck_of(page).locator("#s03 li", has_text="Sequencing is fast")).to_be_visible()


def test_regenerar_beamer_runs_the_beamer_job_and_the_view_then_shows_the_new_pdf(studio_page):
    page = studio_page
    open_project(page, "nexus-go-defense.tex")
    loaded(page_image(page))
    shown = page_image(page).get_attribute("src")

    button = page.get_by_role("region", name="Deck").get_by_role("button", name="Regenerar Beamer")
    button.click()
    job = page.get_by_role("region", name="Tarefas").get_by_role("article", name="Regenerar Beamer")
    expect(job.get_by_role("log")).to_contain_text("regenerado")
    expect(page_image(page)).not_to_have_attribute("src", shown)
    loaded(page_image(page))
    expect(button).to_be_enabled()


def test_the_academic_deck_compiles_in_the_app_data_and_a_click_on_a_title_gives_its_frame_and_line(studio, studio_page):
    page = studio_page
    open_project(page, "nexus-go-academic.tex")
    compiled(page)
    expect(page_image(page)).to_have_accessible_name("Página 1 de 55")
    page.keyboard.press("ArrowRight")
    expect(page_image(page)).to_have_accessible_name("Página 2 de 55")
    loaded(page_image(page))

    pdf = studio.data / "beamer" / "academico-nexus-go-academic" / "nexus-go-academic.pdf"
    click_word(page, pdf, 2, "Roadmap")
    expect(chips(page)).to_have_text(["Roadmap nexus-go-academic.tex:61"])
    expect(source_pane(page)).to_contain_text("nexus-go-academic.tex, linhas 61 a 74")


def test_the_page_image_has_the_pixels_of_the_screen_it_is_shown_on(studio, browser):
    context = browser.new_context(viewport={"width": 1600, "height": 900}, device_scale_factor=2, reduced_motion="reduce")
    try:
        page = context.new_page()
        page.route(lambda url: urlsplit(url).hostname not in ("127.0.0.1", "localhost"), lambda route: route.abort())
        open_studio(page, studio)
        open_project(page, "talk.tex")
        compiled(page)
        loaded(page_image(page))
        natural, shown = page_image(page).evaluate("img => [img.naturalWidth, img.getBoundingClientRect().width]")
        assert 2 * shown - 4 <= natural <= 2 * shown + 170  # rendered in steps of 160 px
    finally:
        context.close()


def test_two_saves_in_a_row_end_on_the_whole_deck_with_both_changes(studio, studio_page):
    page = studio_page
    open_project(page, "talk.tex")
    compiled(page)
    thumbnails(page).nth(7).click()
    click_word(page, talk_pdf(studio), 8, "Questions")
    box = source_pane(page).get_by_role("textbox", name="LaTeX do frame")
    save = source_pane(page).get_by_role("button", name="Salvar")
    expect(box).to_have_value(re.compile("Questions are welcome."))
    n = cards(page).count()  # the cards of this module's earlier saves come back with the page

    track_compiles(page)
    box.fill(box.input_value().replace("Questions are welcome.", "Questions are welcome, please."))
    save.click()
    expect(save).to_be_disabled()
    expect(box).to_have_value(re.compile("welcome, please"))  # saved: the pane holds the saved text
    page.wait_for_function("() => window.compiles.length > 0")  # the first save's compiles have begun
    box.fill(box.input_value().replace("welcome, please.", "welcome, as always."))
    save.click()
    # whatever the order of the compiles, the last one is of the whole deck, with both saves in it
    page.wait_for_function("""() => { const c = window.compiles.at(-1);
        return c && c[0] === 'full' && c[1] === 'ok' && !document.querySelector('.beamer-status progress'); }""",
                           timeout=90_000)
    expect(page_image(page)).to_have_accessible_name("Página 8 de 8")
    expect(bar_status(page)).to_have_text(DONE)
    assert "Questions are welcome, as always." in (studio.kit / TALK).read_text(encoding="utf-8")
    expect(cards(page)).to_have_count(n + 2)
