"""Review fixes in the UI area (findings 2/7, 4, 5, 8, 9, 12, 13).

Each test states the fixed behavior; it fails on the code before its fix and passes after. The server is the
module's fake-agent studio, except the build-failure test, which needs a kit whose build is broken on purpose.
"""
import re

from playwright.sync_api import expect

from tests.e2e.conftest import (center, deck_of, go_slide, open_studio, run_studio, slide_and_step, status_of,
                                 wait_until)
from tests.helpers.kit_copy import make_kit_copy, remove_kit_copy

PART = "deck/src/slides/03-data.html"
LI9_TEXT = "Labels per protein (mean): 25.91 BP, 12.48 CC, 7.55 MF"  # 03-data.html:9:5, s13 fragment 3


def at(page, loc):
    return deck_of(page).locator(f'[data-loc="deck/src/slides/{loc}"]')


def chips(page):
    return page.get_by_role("list", name="Seleção").get_by_role("listitem")


def composer(page):
    return page.get_by_role("textbox", name="Mensagem")


def conversation(page):
    return page.get_by_role("log", name="Conversa")


def send(page, text):
    composer(page).fill(text)
    composer(page).press("Enter")


def top_right(locator):
    b = locator.bounding_box()
    return b["x"] + b["width"], b["y"]


# ---------- finding 2/7: a failed build is shown, not silent ----------
def test_a_failed_deck_build_is_shown_in_the_deck_bar(page):
    kit = make_kit_copy()
    part = kit / PART
    part.write_bytes(part.read_bytes().replace(
        b"Label matrix density", b'<img src="img/no-such-image.png">Label matrix density'))  # missing asset: build fails
    try:
        with run_studio(kit=kit) as studio:
            page.goto(studio.url)
            expect(page.locator("body[data-ready]")).to_be_attached()
            bar = page.get_by_role("region", name="Deck")
            expect(bar.get_by_text("A compilação falhou", exact=False)).to_be_visible()
    finally:
        remove_kit_copy(kit)


# ---------- finding 9: the current chat tab is scrolled into view ----------
def test_the_selected_chat_tab_is_scrolled_into_view_when_many_tabs_overflow(studio_page):
    page = studio_page
    tablist = page.get_by_role("tablist", name="Chats")
    tabs = tablist.get_by_role("tab")
    n = tabs.count()
    for _ in range(4):  # five tabs in a ~250 px row: the last one would sit past the right edge
        page.get_by_role("button", name="Novo chat").click()
    # each click's chat comes back on its own: the row keeps changing (and widening) until the last one is shown
    expect(tabs).to_have_count(n + 4)
    selected = tabs.last
    expect(selected).to_have_attribute("aria-selected", "true")
    row, tab = tablist.bounding_box(), selected.bounding_box()
    assert tab["x"] >= row["x"] - 1 and tab["x"] + tab["width"] <= row["x"] + row["width"] + 1, (row, tab)


# ---------- finding 13: a shell tool card never claims the command ran while it waits or is denied ----------
def test_a_shell_tool_card_does_not_claim_it_ran_while_waiting_or_denied(studio_page):
    page = studio_page
    send(page, "#scenario:bash")  # asks to run "npm run lint": the guard asks the author first
    approval = page.get_by_role("article", name="Aprovação: Bash")
    expect(approval).to_be_visible()
    card = conversation(page).get_by_role("article", name=re.compile("npm run lint"))
    expect(card).to_be_visible()
    expect(card).not_to_contain_text("Rodou")  # it has not run; "Rodou" (ran) would be a lie
    expect(card).to_contain_text("Comando npm run lint")

    approval.get_by_role("button", name="Negar").click()
    expect(card).to_contain_text("negado")
    expect(card).not_to_contain_text("Rodou")


# ---------- finding 12: the deck bar carries the edit hint and the step readout ----------
def test_the_deck_bar_shows_the_edit_hint_and_the_current_step(studio_page):
    page = studio_page
    bar = page.get_by_role("region", name="Deck")
    expect(bar.get_by_text("Duplo clique num texto: edita ali mesmo")).to_be_visible()
    step = page.get_by_role("status", name="Passo atual")
    go_slide(page, 13, 1)
    expect(step).to_have_text(re.compile(r"passo \d+ de \d+"))
    first = step.inner_text()
    go_slide(page, 13, 2)
    expect(step).not_to_have_text(first)  # it follows the deck
    expect(step).to_have_text(re.compile(r"passo \d+ de \d+"))


# ---------- finding 4: a comment pin follows the box whose text matches, not a shifted loc ----------
def test_a_comment_pin_follows_the_box_whose_text_matches_not_the_stored_line(studio, studio_page, api):
    page = studio_page
    for c in api.get(f"{studio.base}/api/comments", headers=studio.headers).json():
        api.delete(f"{studio.base}/api/comments/{c['id']}", headers=studio.headers)
    go_slide(page, 13, 3)
    # the stored loc points at li8 (line 8), but the text is li9's: after a shift the box keeps its text, not its line,
    # so the pin must land on the box whose text matches (li9), never on the neighbour at the stored line
    selection = [{"slideId": "s13", "slide": 13, "step": 3, "part": "03-data.html",
                  "loc": {"file": PART, "line": 8, "col": 5}, "tag": "li", "classes": ["f"],
                  "text": LI9_TEXT, "kind": "text"}]
    created = api.post(f"{studio.base}/api/comments", headers=studio.headers,
                       data={"text": "segue o texto", "selection": selection}).json()
    try:
        pin = deck_of(page).locator(".studio-pin:visible")
        expect(pin).to_have_count(1)
        px, py = center(pin)
        x9, y9 = top_right(at(page, "03-data.html:9:5"))
        x8, y8 = top_right(at(page, "03-data.html:8:5"))
        to9 = abs(px - x9) + abs(py - y9)
        to8 = abs(px - x8) + abs(py - y8)
        assert to9 < to8, (to9, to8)  # the pin sits on li9 (text match), not li8 (stored line)
    finally:
        api.delete(f"{studio.base}/api/comments/{created['id']}", headers=studio.headers)


# ---------- finding 5: a swap re-anchors the selection chip to the new line, never leaving a stale one ----------
def test_a_swap_re_anchors_the_selection_chip_instead_of_leaving_a_stale_line(studio, studio_page, api):
    page = studio_page
    part = studio.kit / PART
    before = part.read_bytes()
    page.get_by_role("button", name="Selecionar (S)").click()
    go_slide(page, 13, 3)
    page.mouse.click(*center(at(page, "03-data.html:9:5")))
    expect(chips(page)).to_have_count(1)
    expect(chips(page).first).to_contain_text("03-data.html:9")

    # trigger the edit through the API, not the composer (the composer would clear the live selection on send): an
    # agent turn inserts a line above the bullets, so li9 moves from line 9 to line 10 and the slide swaps in place
    chat_id = page.evaluate("() => studio.chat.current().id")
    res = api.post(f"{studio.base}/api/chats/{chat_id}/messages", headers=studio.headers,
                   data={"text": "#scenario:insert-line"})
    assert res.status == 202, res.text()
    try:
        expect(chips(page).first).to_contain_text("03-data.html:10")  # re-anchored, not left at :9
        selection = page.evaluate("() => studio.selection.get()")
        assert selection and selection[0]["loc"]["line"] == 10
    finally:
        wait_until(lambda: not status_of(studio, api)["busy"], message="the agent turn to end")
        turn = res.json()["turnId"]
        undo = api.post(f"{studio.base}/api/turns/{turn}/undo", headers=studio.headers, data={})
        assert undo.status == 200, undo.text()
        assert part.read_bytes() == before


# ---------- finding 8: an in-place edit refused while a turn runs keeps the typed text for a retry ----------
def test_an_in_place_edit_refused_while_a_turn_runs_keeps_the_typed_text(studio, studio_page, api):
    page = studio_page
    part = studio.kit / PART
    before = part.read_bytes()
    chat_id = page.evaluate("() => studio.chat.current().id")
    send(page, "#scenario:long")  # holds the turn lock
    wait_until(lambda: status_of(studio, api)["busy"], message="the turn to take the lock")
    try:
        go_slide(page, 14, 2)
        at(page, "03-data.html:36:5").dblclick()
        editor = deck_of(page).get_by_role("textbox", name="Editar texto")
        editor.fill("Texto digitado durante o turno")
        editor.press("Enter")
        expect(page.get_by_role("alert").filter(has_text="Outro pedido está em andamento")).to_be_visible()
        expect(editor).to_have_count(1)  # the editor stays open: the typing is not thrown away
        expect(editor).to_have_text("Texto digitado durante o turno")
        assert part.read_bytes() == before
    finally:
        api.post(f"{studio.base}/api/chats/{chat_id}/interrupt", headers=studio.headers, data={})
        wait_until(lambda: not status_of(studio, api)["busy"], message="the turn to end")
