"""Number provenance: GET /api/provenance and the "Origem" chip on hover in the deck."""
import re

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import deck_of, go_slide, run_studio, slide_and_step
from tests.helpers.kit_copy import make_kit_copy, remove_kit_copy

TEX = "source/thesis/dissertation.tex"
INVENTED = "987.65"  # on no .tex line and in no audit row


def edit(file, old, new):
    text = file.read_text(encoding="utf8")
    assert old in text
    file.write_text(text.replace(old, new, 1), encoding="utf8")


@pytest.fixture(scope="module")
def studio():
    """The module's studio, on a kit copy whose s13 also shows an invented number and a value of its table."""
    kit = make_kit_copy()
    try:
        edit(kit / "deck/src/slides/03-data.html", '<ul class="b" style="grid-column: 8 / 13">',
             f'<ul class="b" style="grid-column: 8 / 13">\n    <li>Invented: {INVENTED}</li>\n'
             '    <li>Training proteins: 73,768</li>')
        with run_studio(kit=kit) as s:
            yield s
    finally:
        remove_kit_copy(kit)


def numbers(index, slide):
    return {e["number"]: e for e in index["slides"][slide]}


def test_api_provenance_serves_the_number_index_of_the_slide_sources_and_follows_them(studio, api):
    url = f"{studio.base}/api/provenance"
    assert api.get(url).status == 401
    res = api.get(url, headers=studio.headers)
    assert res.status == 200
    s13 = numbers(res.json(), "s13")
    tex = (studio.kit / TEX).read_text(encoding="utf8").split("\n")
    assert s13["25.91"]["reason"] is None
    assert s13["25.91"]["sources"]
    for src in s13["25.91"]["sources"]:
        assert src["file"] == TEX
        assert "25.91" in tex[src["line"] - 1]
        assert "25.91" in src["snippet"]
    assert s13[INVENTED] == {"number": INVENTED, "sources": [], "reason": None}
    assert numbers(res.json(), "s07")["157"] == {"number": "157", "sources": [], "reason": "VISAPP pages"}

    part = studio.kit / "deck/src/slides/03-data.html"
    before = part.read_text(encoding="utf8")
    try:
        edit(part, f"<li>Invented: {INVENTED}</li>", "<li>Invented: 876.54</li>")
        s13 = numbers(api.get(url, headers=studio.headers).json(), "s13")
        assert INVENTED not in s13
        assert s13["876.54"] == {"number": "876.54", "sources": [], "reason": None}
    finally:
        part.write_text(before, encoding="utf8")


TEXT_CENTER = """(el, text) => {
    const walk = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    for (let t; (t = walk.nextNode());) {
        const i = t.data.indexOf(text);
        if (i < 0) continue;
        const r = document.createRange();
        r.setStart(t, i);
        r.setEnd(t, i + text.length);
        const b = r.getBoundingClientRect();
        return [b.x + b.width / 2, b.y + b.height / 2];
    }
    throw new Error(`no text ${text}`);
}"""


def hover_text(page, locator, text):
    """Put the mouse on the middle of `text` inside the deck element `locator`."""
    x, y = locator.evaluate(TEXT_CENTER, text)
    frame = deck_of(page).locator("html").bounding_box()  # the frame's viewport, in page coordinates
    page.mouse.move(0, 0)
    page.mouse.move(frame["x"] + x, frame["y"] + y)


def chip(page):
    return deck_of(page).get_by_role("tooltip")


def origem(page):
    return page.get_by_role("region", name="Deck").get_by_role("button", name="Origem")


def expect_tex_chip(page, studio, number):
    """The chip names a dissertation.tex line that holds `number`, and shows that line (the snippet)."""
    expect(chip(page)).to_be_visible()
    expect(chip(page)).to_contain_text(number)  # the hovered number itself is not repeated: this is the snippet
    found = re.search(r"dissertation\.tex:L(\d+)", chip(page).inner_text())
    assert found, chip(page).inner_text()
    assert number in (studio.kit / TEX).read_text(encoding="utf8").split("\n")[int(found[1]) - 1]


def test_with_origem_on_hovering_a_number_shows_the_dissertation_line_it_comes_from(studio, studio_page):
    page = studio_page
    labels = deck_of(page).locator("#s13 li").filter(has_text="Labels per protein")
    density = deck_of(page).locator("#s13 .dens").first
    go_slide(page, 13, 3)
    expect(origem(page)).to_have_attribute("aria-pressed", "false")
    hover_text(page, labels, "25.91")
    expect(chip(page)).to_have_count(0)

    origem(page).click()
    expect(origem(page)).to_have_attribute("aria-pressed", "true")
    hover_text(page, labels, "25.91")
    expect_tex_chip(page, studio, "25.91")
    hover_text(page, density, "5.18")  # another number, whose first line is another one
    expect(chip(page)).to_have_count(1)
    expect_tex_chip(page, studio, "5.18")


def test_a_number_the_audit_allows_shows_its_reason_and_one_with_no_source_a_red_sem_origem_chip(studio_page):
    page = studio_page
    origem(page).click()
    go_slide(page, 7, 3)
    hover_text(page, deck_of(page).locator("#s07 .pub .v").first, "157")  # VISAPP 2026 · published, pp. 157–166
    expect(chip(page)).to_contain_text("VISAPP pages")
    expect(chip(page)).not_to_contain_text("dissertation.tex")

    go_slide(page, 13, 0)
    hover_text(page, deck_of(page).locator("#s13 li").filter(has_text="Invented"), INVENTED)
    expect(chip(page)).to_contain_text("sem origem")
    assert chip(page).evaluate("(c) => getComputedStyle(c).borderColor") == "rgb(194, 65, 12)"  # the studio's --warn


def test_a_number_the_tex_has_only_inside_another_term_or_in_a_comment_gets_a_weaker_chip(studio, studio_page):
    page = studio_page
    origem(page).click()
    go_slide(page, 15, 1)
    hover_text(page, deck_of(page).locator("#s15 figcaption").first, "4.2")  # "Fig. 4.2": the .tex has it in a comment
    expect_tex_chip(page, studio, "4.2")
    expect(chip(page)).to_contain_text("Só aparece dentro de outro termo ou num comentário.")
    assert chip(page).evaluate("(c) => getComputedStyle(c).borderStyle") == "dashed"

    go_slide(page, 13, 3)
    hover_text(page, deck_of(page).locator("#s13 li").filter(has_text="Labels per protein"), "25.91")
    expect_tex_chip(page, studio, "25.91")
    expect(chip(page)).not_to_contain_text("Só aparece")
    assert chip(page).evaluate("(c) => getComputedStyle(c).borderStyle") == "solid"


def test_numbers_the_build_drew_numbers_not_revealed_yet_and_other_words_get_no_chip(studio, studio_page):
    page = studio_page
    origem(page).click()
    s13 = deck_of(page).locator("#s13")
    authored = s13.locator("li").filter(has_text="Training proteins")
    go_slide(page, 13, 1)  # the corpus table is in, "Labels per protein" (step 3) is still at opacity 0
    for box, text in [(authored, "Training"),
                      (s13.locator("td").filter(has_text="73,768"), "73,768"),  # the same value, in the table built from the .tex
                      (s13.locator("li").filter(has_text="Labels per protein"), "25.91")]:
        hover_text(page, authored, "73,768")
        expect_tex_chip(page, studio, "73,768")
        hover_text(page, box, text)
        expect(chip(page)).to_have_count(0)


def test_origem_leaves_the_deck_dom_the_picker_and_the_deck_keys_alone(studio, studio_page):
    page = studio_page
    stage = deck_of(page).locator("#stage")
    labels = deck_of(page).locator("#s13 li").filter(has_text="Labels per protein")
    go_slide(page, 13, 3)
    before = stage.evaluate("(s) => s.outerHTML")
    origem(page).click()
    for number in ["25.91", "12.48", "7.55"]:
        hover_text(page, labels, number)
        expect_tex_chip(page, studio, number)
    assert stage.evaluate("(s) => s.outerHTML") == before

    # select mode: the box under the chip's number is still what a click selects, and the slide stays
    select = page.get_by_role("button", name="Selecionar (S)")
    select.click()
    hover_text(page, labels, "25.91")
    expect_tex_chip(page, studio, "25.91")
    page.mouse.down()
    page.mouse.up()
    chips = page.get_by_role("list", name="Seleção").get_by_role("listitem")
    expect(chips).to_have_count(1)
    expect(chips.first).to_contain_text("s13 li")
    assert slide_and_step(page) == (13, 3)
    select.click()

    page.evaluate("() => studio.deck.win().focus()")  # the toolbar button has the keyboard now
    page.keyboard.press("ArrowLeft")
    assert slide_and_step(page) == (13, 2)


def test_origem_stays_on_across_a_deck_reload_and_then_reads_the_sources_as_they_are(studio, studio_page):
    page = studio_page
    pages = deck_of(page).locator("#s07 .pub .v").first
    origem(page).click()
    go_slide(page, 7, 3)
    hover_text(page, pages, "157")
    expect(chip(page)).to_contain_text("VISAPP pages")

    audit = studio.kit / "qa/number_audit.md"
    before = audit.read_text(encoding="utf8")
    try:
        edit(audit, "| 7 | 157 | VISAPP pages |", "| 7 | 157 | VISAPP page range |")
        page.evaluate("() => studio.deck.reload()")  # what a deck-reload event does
        hover_text(page, pages, "157")
        expect(chip(page)).to_contain_text("VISAPP page range")
    finally:
        audit.write_text(before, encoding="utf8")
    expect(origem(page)).to_have_attribute("aria-pressed", "true")


def test_leaving_the_deck_a_step_that_hides_the_number_and_turning_origem_off_hide_the_chip(studio, studio_page):
    page = studio_page
    labels = deck_of(page).locator("#s13 li").filter(has_text="Labels per protein")
    go_slide(page, 13, 3)
    origem(page).click()
    hover_text(page, labels, "25.91")
    expect_tex_chip(page, studio, "25.91")
    page.mouse.move(5, 5)  # onto the studio page's header
    expect(chip(page)).to_have_count(0)

    hover_text(page, labels, "25.91")
    expect(chip(page)).to_be_visible()
    page.evaluate("() => studio.deck.go(13, 2)")  # the pointer rests; the number is not revealed at step 2
    expect(chip(page)).to_have_count(0)

    page.evaluate("() => studio.deck.go(13, 3)")
    hover_text(page, labels, "25.91")
    expect(chip(page)).to_be_visible()
    origem(page).press("Enter")  # by keyboard: the pointer stays on the number
    expect(origem(page)).to_have_attribute("aria-pressed", "false")
    expect(chip(page)).to_have_count(0)
    hover_text(page, labels, "25.91")
    expect(chip(page)).to_have_count(0)


def test_after_a_direct_edit_swaps_the_slide_in_place_the_chip_knows_its_new_numbers(studio, studio_page):
    page = studio_page
    invented = deck_of(page).locator("#s13 li").filter(has_text="Invented")
    file, line, col = invented.get_attribute("data-loc").rsplit(":", 2)
    go_slide(page, 13, 0)
    origem(page).click()
    hover_text(page, invented, INVENTED)
    expect(chip(page)).to_contain_text("sem origem")
    page.mouse.move(5, 5)
    expect(chip(page)).to_have_count(0)

    page.evaluate("() => { studio.deck.win().marker = 'no reload'; }")
    edit = {"loc": {"file": file, "line": int(line), "col": int(col)}, "childIndex": 0,
            "oldText": f"Invented: {INVENTED}", "newText": "Invented: 876.54"}
    page.evaluate("(edit) => { window.saved = studio.api('/api/edit-text', edit); }", edit)
    edited = deck_of(page).locator("#s13 li").filter(has_text="Invented: 876.54")
    expect(edited).to_be_visible()
    hover_text(page, edited, "876.54")
    expect(chip(page)).to_contain_text("sem origem")
    assert page.evaluate("() => studio.deck.win().marker") == "no reload"  # swapped in place, not reloaded

    saved = page.evaluate("() => window.saved")
    assert saved["status"] == 200
    assert page.evaluate("(id) => studio.api(`/api/turns/${id}/undo`, {})", saved["data"]["turnId"])["status"] == 200
