"""The EN | PT switch on NEXUS-GO's own layout (bug of 2026-11-04: PT stayed off with the real kit): the Portuguese
deck is a tree of its own, deck/src-pt, built with `build.mjs --pt`. With PT on screen the studio shows, selects and
edits deck/src-pt's files, builds with --pt, and Exportar PDF follows the language. No "Traduzir" for it."""
import json

from playwright.sync_api import expect

from tests.e2e.conftest import built, deck_of

EN = "Master's dissertation defense"
PT = "Defesa de dissertação de mestrado"


def switch(page):
    return page.get_by_role("radiogroup", name="Idioma do deck")


def answers(page):
    return page.get_by_role("log", name="Conversa").get_by_role("article", name="Claude")


def export_log(page):
    """Run Exportar PDF in the page and return its log lines."""
    return page.evaluate("""async () => {
        const lines = [];
        const done = new Promise((resolve) => {
            const off = studio.on('job', (e) => {
                if (e.line) lines.push(e.line);
                if (e.state !== 'running') { off(); resolve(); }
            });
        });
        await studio.api('/api/jobs/export-pdf', {});
        await done;
        return lines;
    }""")


def test_portuguese_is_ready_from_the_tree_and_there_is_nothing_to_translate(studio, studio_page, api):
    page = studio_page
    expect(switch(page).get_by_role("radio", name="Inglês")).to_have_attribute("aria-checked", "true")
    expect(switch(page).get_by_role("radio", name="Português")).to_be_enabled()
    expect(page.get_by_role("button", name="Traduzir para português")).to_be_hidden()
    data = api.get(f"{studio.base}/api/language", headers=studio.headers).json()
    assert {l["code"]: (l["available"], l["tree"]) for l in data["languages"]} == {"en": (True, False), "pt": (True, True)}


def test_pt_shows_and_edits_the_src_pt_tree_and_the_export_follows_it(studio, studio_page, api):
    page = studio_page
    switch(page).get_by_role("radio", name="Português").click()
    expect(switch(page).get_by_role("radio", name="Português")).to_have_attribute("aria-checked", "true")
    expect(deck_of(page).get_by_text(PT)).to_be_visible(timeout=30_000)
    assert built(studio, api)["ok"]
    # every box points at deck/src-pt: what is selected and edited is the Portuguese source
    expect(deck_of(page).locator("[data-loc^='deck/src/slides/']")).to_have_count(0)
    expect(deck_of(page).locator("[data-loc^='deck/src-pt/slides/']").first).to_be_attached()
    expect(page.get_by_role("button", name="Traduzir para inglês")).to_be_hidden()
    # the Files pane lists the Portuguese slides, open
    files = page.get_by_role("region", name="Arquivos")
    expect(files).to_contain_text("deck/src-pt/slides/")
    expect(files).not_to_contain_text("deck/src/slides/")
    expect(files.get_by_role("button", name="00-opening.html")).to_be_visible()
    # nothing was copied around
    assert not (studio.kit / "deck" / "src" / "i18n").exists()
    assert json.loads((studio.data / "settings.json").read_text(encoding="utf-8"))["language"] == "pt"

    assert any("stand-in for the export-pdf job (pt)" in line for line in export_log(page))

    page.get_by_role("textbox", name="Mensagem").fill("#scenario:message")
    page.get_by_role("textbox", name="Mensagem").press("Enter")
    expect(answers(page).last).to_contain_text("deck/src-pt/slides are now the Brazilian Portuguese version")


def test_an_in_place_edit_in_pt_changes_the_src_pt_file_only(studio, studio_page, api):
    page = studio_page
    en_file = (studio.kit / "deck" / "src" / "slides" / "00-opening.html").read_bytes()
    target = deck_of(page).get_by_text(PT)
    target.dblclick()
    editor = deck_of(page).locator(".studio-editing")
    expect(editor).to_be_visible()
    editor.fill(PT + " editada")
    editor.press("Enter")
    pt_file = studio.kit / "deck" / "src-pt" / "slides" / "00-opening.html"
    card = page.get_by_role("article").filter(has_text="Texto editado em 00-opening.html")
    expect(card).to_be_visible()  # the save is done (the typed text shows before it)
    assert PT + " editada" in pt_file.read_text(encoding="utf-8")
    assert (studio.kit / "deck" / "src" / "slides" / "00-opening.html").read_bytes() == en_file


def test_back_to_en_the_studio_works_on_deck_src_again(studio, studio_page, api):
    page = studio_page
    switch(page).get_by_role("radio", name="Inglês").click()
    expect(switch(page).get_by_role("radio", name="Inglês")).to_have_attribute("aria-checked", "true")
    expect(deck_of(page).get_by_text(EN)).to_be_visible(timeout=30_000)
    assert built(studio, api)["ok"]
    expect(deck_of(page).locator("[data-loc^='deck/src-pt/slides/']")).to_have_count(0)
    expect(page.get_by_role("region", name="Arquivos")).not_to_contain_text("deck/src-pt/slides/")
    assert any(line.strip() == "stand-in for the export-pdf job" for line in export_log(page))
