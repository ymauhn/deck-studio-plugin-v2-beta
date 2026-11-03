"""Slice 3: the picker (select mode, hover outline, selection chips, SPEC Selection shape)."""
import json
import re
import sys

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import built, center, deck_of, go_slide, slide_and_step, wait_until


@pytest.fixture(scope="module")
def studio_args(tmp_path_factory):
    """The module's studio build first waits 4 s while the kit holds a file named slow-build."""
    config = tmp_path_factory.mktemp("cfg") / "config.json"
    config.write_text(json.dumps({"studioBuild": [
        sys.executable, "-c", "import os, subprocess, sys, time; os.path.exists('slow-build') and time.sleep(4); "
        "sys.exit(subprocess.call(['node', 'deck/build.mjs', '--studio']))"]}), encoding="utf-8")
    return ["--config", config]


def at(page, loc):
    return deck_of(page).locator(f'[data-loc="deck/src/slides/{loc}"]')


def select_mode(page):
    page.get_by_role("button", name="Selecionar (S)").click()


def chips(page):
    return page.get_by_role("list", name="Seleção").get_by_role("listitem")


def expect_same_box(a, b):
    x, y = a.bounding_box(), b.bounding_box()
    for k in ["x", "y", "width", "height"]:
        assert abs(x[k] - y[k]) < 2, f"{k}: {x[k]} vs {y[k]}"


def test_the_s_key_when_no_text_field_has_focus_and_the_toolbar_button_toggle_select_mode(studio_page):
    page = studio_page
    button = page.get_by_role("button", name="Selecionar (S)")
    expect(button).to_have_attribute("aria-pressed", "false")

    deck_of(page).locator("body").press("s")  # the deck has the focus after loading
    expect(button).to_have_attribute("aria-pressed", "true")
    button.click()
    expect(button).to_have_attribute("aria-pressed", "false")
    button.press("s")  # studio page, focus on a button
    expect(button).to_have_attribute("aria-pressed", "true")

    composer = page.get_by_role("textbox", name="Mensagem")
    composer.click()
    composer.press("s")
    expect(composer).to_have_value("s")
    expect(button).to_have_attribute("aria-pressed", "true")


def test_hover_outlines_the_box_under_the_pointer_skipping_elements_at_opacity_0_or_visibility_hidden(studio_page):
    page = studio_page
    select_mode(page)
    outline = deck_of(page).locator("#studio-hover")
    item = at(page, "03-data.html:9:5")  # fragment 3 of s13
    around = at(page, "03-data.html:7:3")  # the list that holds it

    go_slide(page, 13, 3)
    page.mouse.move(*center(item))
    expect(outline).to_be_visible()
    expect_same_box(outline, item)

    go_slide(page, 13, 2)  # the item is not revealed yet (opacity 0): the list around it is what shows there
    page.mouse.move(0, 0)
    page.mouse.move(*center(item))
    expect_same_box(outline, around)

    go_slide(page, 13, 3)
    item.evaluate("(el) => { el.style.visibility = 'hidden'; }")
    page.mouse.move(0, 0)
    page.mouse.move(*center(item))
    expect_same_box(outline, around)


def test_a_click_selects_the_box_without_advancing_the_slide_and_shows_a_chip_in_the_composer(studio_page):
    page = studio_page
    select_mode(page)
    go_slide(page, 13, 3)
    page.mouse.click(*center(at(page, "03-data.html:9:5")))  # right two thirds: the deck would go forward

    assert slide_and_step(page) == (13, 3)
    expect(chips(page)).to_have_count(1)
    for part in ["s13", "li", "03-data.html:9"]:
        expect(chips(page).first).to_contain_text(part)


def test_shift_click_adds_a_second_chip_and_esc_clears_the_selection(studio_page):
    page = studio_page
    select_mode(page)
    go_slide(page, 13, 3)
    outlines = deck_of(page).locator(".studio-selected:visible")
    page.mouse.click(*center(at(page, "03-data.html:9:5")))
    page.keyboard.down("Shift")
    page.mouse.click(*center(at(page, "03-data.html:8:5")))
    page.keyboard.up("Shift")
    expect(chips(page)).to_have_count(2)
    expect(chips(page).nth(0)).to_contain_text("03-data.html:9")
    expect(chips(page).nth(1)).to_contain_text("03-data.html:8")
    expect(outlines).to_have_count(2)

    deck_of(page).locator("body").press("Escape")  # focus in the deck
    expect(chips(page)).to_have_count(0)
    expect(outlines).to_have_count(0)

    page.mouse.click(*center(at(page, "03-data.html:9:5")))
    expect(chips(page)).to_have_count(1)
    page.get_by_role("textbox", name="Mensagem").press("Escape")  # focus in the studio page
    expect(chips(page)).to_have_count(0)
    expect(outlines).to_have_count(0)


def test_a_click_on_a_generated_table_or_inside_a_component_selects_the_table_or_the_component_container(studio_page):
    page = studio_page
    select_mode(page)
    go_slide(page, 13, 3)
    page.mouse.click(*center(deck_of(page).locator("#s13 table td").nth(6)))  # a cell of the corpus table
    expect(chips(page)).to_have_count(1)
    for part in ["s13", "tabela gerada", "03-data.html:5"]:
        expect(chips(page).first).to_contain_text(part)

    go_slide(page, 21, 0)
    pipe = deck_of(page).locator('#s21 [data-component="INT-PIPE"]')
    page.mouse.click(*center(pipe))
    expect(chips(page)).to_have_count(1)
    for part in ["s21", "INT-PIPE", "04-method.html:79"]:
        expect(chips(page).first).to_contain_text(part)

    # an authored element inside a component (it has its own source location) still selects the component
    pipe.evaluate("""(el) => el.insertAdjacentHTML('beforeend', '<p id="authored" '
        + 'data-loc="deck/src/slides/04-method.html:80:5" '
        + 'style="position:absolute; left:0; top:0; z-index:9; margin:0; background:#fff">fallback</p>')""")
    page.mouse.click(*center(deck_of(page).locator("#authored")))
    expect(chips(page)).to_have_count(1)
    for part in ["s21", "INT-PIPE", "04-method.html:79"]:
        expect(chips(page).first).to_contain_text(part)


def test_the_selection_has_the_spec_shape_and_reaches_the_studio_page_by_postmessage_from_its_own_origin_only(
        studio, studio_page):
    page = studio_page
    select_mode(page)
    go_slide(page, 13, 3)
    page.evaluate("""() => { window.received = new Promise((resolve) => addEventListener('message', (e) => {
        if (e.data?.selection?.length) resolve({ origin: e.origin,
            fromDeck: e.source === document.querySelector('iframe').contentWindow, selection: e.data.selection });
    })); }""")
    page.mouse.click(*center(at(page, "03-data.html:9:5")))

    received = page.evaluate("() => window.received")
    assert received["origin"] == studio.base
    assert received["fromDeck"] is True
    [selection] = received["selection"]
    outer_html, rect = selection.pop("outerHTML"), selection.pop("rect")
    assert selection == {
        "slideId": "s13", "slide": 13, "step": 3, "part": "03-data.html",
        "loc": {"file": "deck/src/slides/03-data.html", "line": 9, "col": 5},
        "tag": "li", "classes": ["f"], "text": "Labels per protein (mean): 25.91 BP, 12.48 CC, 7.55 MF",
        "kind": "text",
    }
    assert re.fullmatch(r"<li [^>]*>Labels per protein \(mean\): 25\.91 BP, 12\.48 CC, 7\.55 MF</li>", outer_html)
    assert sorted(rect) == ["h", "w", "x", "y"] and all(isinstance(v, int) for v in rect.values())
    # rect is in slide units (1600 x 900): the list sits in grid columns 8 to 13, the right part of the slide
    assert rect["x"] > 800
    assert rect["x"] + rect["w"] <= 1600
    assert rect["y"] + rect["h"] <= 900

    # a page from another origin posting a selection is ignored
    page.evaluate("""() => new Promise((resolve) => {
        addEventListener('message', (e) => { if (e.origin === 'null') resolve(); });
        const evil = document.createElement('iframe');
        evil.src = `data:text/html,<script>parent.postMessage({ type: 'studio:selection', selection: [{ slideId: 's99',
          tag: 'div', part: 'evil.html', kind: 'text', loc: { file: 'evil.html', line: 1, col: 1 } }] }, '*')</script>`;
        document.body.append(evil);
    })""")
    expect(chips(page)).to_have_count(1)
    expect(chips(page).first).to_contain_text("03-data.html:9")


def test_studio_picker_selection_at_gives_the_selection_of_the_topmost_visible_box_at_a_point_in_slide_units(
        studio_page):
    page = studio_page

    def selection_at(x, y):
        return deck_of(page).locator("html").evaluate("(_, [x, y]) => window.studioPicker.selectionAt(x, y)", [x, y])

    page.evaluate("""() => { window.received = new Promise((resolve) => addEventListener('message', (e) => {
        if (e.data?.selection?.length) resolve(e.data.selection[0]);
    })); }""")
    select_mode(page)
    go_slide(page, 13, 3)
    page.mouse.click(*center(at(page, "03-data.html:9:5")))
    clicked = page.evaluate("() => window.received")
    select_mode(page)  # off again: selectionAt works in either mode
    x, y = clicked["rect"]["x"] + clicked["rect"]["w"] / 2, clicked["rect"]["y"] + clicked["rect"]["h"] / 2

    assert selection_at(x, y) == clicked
    go_slide(page, 13, 2)  # not revealed yet: the list around it is the topmost visible box there
    assert selection_at(x, y)["loc"] == {"file": "deck/src/slides/03-data.html", "line": 7, "col": 3}
    assert selection_at(1700, 450) is None  # outside the slide
    assert selection_at(-5, 450) is None


def test_a_click_picks_nothing_while_the_deck_rebuilds_and_picks_again_once_the_new_deck_is_shown(
        studio, studio_page, api):
    """SPEC story 16: while a build runs the deck may show boxes its sources no longer have."""
    page = studio_page
    built(studio, api)
    select_mode(page)
    go_slide(page, 13, 3)
    marker = studio.kit / "slow-build"
    marker.touch()
    try:
        page.evaluate("""() => { studio.deck.win().old = true;
            window.building = new Promise((resolve) => {
                const off = studio.on('build', (b) => { if (b.running) { off(); resolve(); } });
            });
            studio.chat.send('#scenario:rebuild'); }""")
        page.evaluate("() => window.building")  # the page has heard of the build
        page.mouse.click(*center(at(page, "03-data.html:9:5")))
        page.wait_for_timeout(500)  # a pick shows its chip within a few ms
        expect(chips(page)).to_have_count(0)
    finally:
        marker.unlink()

    wait_until(lambda: page.evaluate("""() => { const w = studio.deck.win();
        return !w.old && w.document.readyState === 'complete' && w.deck?.state().fragment === 3; }"""),
               timeout=30, message="the rebuilt deck, back at slide 13, step 3")
    page.mouse.click(*center(at(page, "03-data.html:9:5")))
    expect(chips(page)).to_have_count(1)
    expect(chips(page).first).to_contain_text("03-data.html:9")
