"""Comment batches: comments on boxes across slides, pins on the deck, a panel, and one chat turn that applies them."""
import re
import shutil
import tempfile
from pathlib import Path

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import center, deck_of, go_slide, open_studio, run_studio, slide_and_step, wait_until
from tests.helpers.kit_copy import make_kit_copy, remove_kit_copy

# Selection items as the picker makes them (SPEC "Selection")
LI9 = {"slideId": "s13", "slide": 13, "step": 3, "part": "03-data.html",
       "loc": {"file": "deck/src/slides/03-data.html", "line": 9, "col": 5}, "tag": "li", "classes": ["f"],
       "text": "Labels per protein (mean): 25.91 BP, 12.48 CC, 7.55 MF", "kind": "text"}
LI8 = {"slideId": "s13", "slide": 13, "step": 3, "part": "03-data.html",
       "loc": {"file": "deck/src/slides/03-data.html", "line": 8, "col": 5}, "tag": "li", "classes": ["f"],
       "text": "80 / 10 / 10 split, disjoint at protein level, no temporal or homology constraint", "kind": "text"}
PIPE = {"slideId": "s21", "slide": 21, "step": 0, "part": "04-method.html",
        "loc": {"file": "deck/src/slides/04-method.html", "line": 79, "col": 3}, "tag": "div", "classes": ["col-w"],
        "kind": "component", "component": "INT-PIPE"}


def at(page, loc):
    return deck_of(page).locator(f'[data-loc="deck/src/slides/{loc}"]')


def chips(page):
    return page.get_by_role("list", name="Seleção").get_by_role("listitem")


def conversation(page):
    return page.get_by_role("log", name="Conversa")


def comments_of(studio, api):
    return api.get(f"{studio.base}/api/comments", headers=studio.headers).json()


def add(studio, api, text, selection):
    res = api.post(f"{studio.base}/api/comments", headers=studio.headers, data={"text": text, "selection": selection})
    assert res.status == 201
    return res.json()


def pins(page):
    return deck_of(page).locator(".studio-pin:visible")


def top_right(locator):
    b = locator.bounding_box()
    return b["x"] + b["width"], b["y"]


@pytest.fixture
def studio_page(page, studio, api):
    """The studio page, opened with no comments left from other tests."""
    for c in comments_of(studio, api):
        api.delete(f"{studio.base}/api/comments/{c['id']}", headers=studio.headers)
    open_studio(page, studio)
    return page


def test_with_boxes_selected_c_or_the_comentar_button_opens_an_input_and_enter_stores_the_comment_with_its_selection(
        studio, studio_page, api):
    page = studio_page
    button = page.get_by_role("button", name="Comentar (C)")
    expect(button).to_be_disabled()  # nothing selected yet

    page.get_by_role("button", name="Selecionar (S)").click()
    go_slide(page, 13, 3)
    page.mouse.click(*center(at(page, "03-data.html:9:5")))
    page.keyboard.down("Shift")
    page.mouse.click(*center(at(page, "03-data.html:8:5")))
    page.keyboard.up("Shift")
    expect(chips(page)).to_have_count(2)

    deck_of(page).locator("body").press("c")  # the deck has the focus
    field = page.get_by_role("textbox", name="Comentário")
    expect(field).to_be_focused()
    expect(field).to_have_value("")
    field.fill("Encurte os dois")
    field.press("Enter")
    expect(field).to_be_hidden()
    expect(chips(page)).to_have_count(0)  # the boxes now carry the comment

    [comment] = comments_of(studio, api)
    assert comment["text"] == "Encurte os dois"
    assert [(s["slideId"], s["tag"], s["loc"]) for s in comment["selection"]] == [
        ("s13", "li", {"file": "deck/src/slides/03-data.html", "line": 9, "col": 5}),
        ("s13", "li", {"file": "deck/src/slides/03-data.html", "line": 8, "col": 5})]

    # the button opens it too; Esc closes it without a comment and keeps the selection
    page.mouse.click(*center(at(page, "03-data.html:9:5")))
    button.click()
    field.fill("descartado")
    field.press("Escape")
    expect(field).to_be_hidden()
    expect(chips(page)).to_have_count(1)
    assert len(comments_of(studio, api)) == 1

    # and so does C on the studio page, outside text fields
    page.get_by_role("button", name="Selecionar (S)").press("c")
    expect(field).to_be_focused()
    field.press("Escape")
    page.get_by_role("textbox", name="Mensagem").press("c")
    expect(field).to_be_hidden()


def test_numbered_pins_mark_the_commented_boxes_while_their_slide_shows_and_the_deck_dom_stays_the_same(
        studio, studio_page, api):
    page = studio_page
    go_slide(page, 13, 3)
    slide = deck_of(page).locator("#s13")
    before = slide.evaluate("(el) => el.outerHTML")

    add(studio, api, "um", [LI9])
    add(studio, api, "dois", [PIPE])  # slide 21: numbered after the two comments on slide 13
    add(studio, api, "três", [LI8, LI9])
    expect(pins(page)).to_have_text(["1", "2", "2"])
    first = pins(page).filter(has_text="1")
    x, y = center(first)
    corner_x, corner_y = top_right(at(page, "03-data.html:9:5"))
    assert abs(x - corner_x) < 20 and abs(y - corner_y) < 20
    # an overlay over the deck: the slide's own DOM is untouched and no pin lives inside the deck
    assert slide.evaluate("(el) => el.outerHTML") == before
    expect(deck_of(page).locator("#deck .studio-pin")).to_have_count(0)

    go_slide(page, 12)
    expect(pins(page)).to_have_count(0)
    go_slide(page, 21)
    expect(pins(page)).to_have_text(["3"])
    x, y = center(pins(page))
    corner_x, corner_y = top_right(deck_of(page).locator('#s21 [data-component="INT-PIPE"]'))
    assert abs(x - corner_x) < 20 and abs(y - corner_y) < 20

    page.evaluate("() => studio.deck.reload()")  # a rebuilt deck gets its pins back
    expect(pins(page)).to_have_text(["3"])


def test_the_comments_panel_lists_the_comments_by_slide_with_go_to_edit_and_delete(studio, studio_page, api):
    page = studio_page
    panel = page.get_by_role("region", name="Comentários")
    expect(panel).to_be_hidden()  # no comments yet

    add(studio, api, "mostre a figura inteira", [PIPE])
    add(studio, api, "mais curto", [LI9])
    items = panel.get_by_role("listitem")
    expect(items).to_have_text([re.compile(r"^1.*s13.*mais curto"), re.compile(r"^2.*s21.*mostre a figura inteira")])

    items.nth(1).get_by_role("button", name="Ir ao slide").click()
    assert slide_and_step(page) == (21, 0)
    items.nth(0).get_by_role("button", name="Ir ao slide").click()
    assert slide_and_step(page) == (13, 3)
    expect(pins(page)).to_have_text(["1"])

    items.nth(0).get_by_role("button", name="Editar").click()
    field = items.nth(0).get_by_role("textbox", name="Comentário")
    expect(field).to_be_focused()
    expect(field).to_have_value("mais curto")
    field.fill("descartado")
    field.press("Escape")
    expect(field).to_have_count(0)
    expect(items.nth(0)).to_contain_text("mais curto")
    items.nth(0).get_by_role("button", name="Editar").click()
    field.fill("bem mais curto")
    field.press("Enter")
    expect(field).to_have_count(0)
    expect(items.nth(0)).to_contain_text("bem mais curto")

    items.nth(1).get_by_role("button", name="Excluir").click()
    expect(items).to_have_count(1)
    assert [c["text"] for c in comments_of(studio, api)] == ["bem mais curto"]

    open_studio(page, studio)  # the server keeps them
    expect(items).to_have_text([re.compile(r"^1.*s13.*bem mais curto")])
    items.first.get_by_role("button", name="Excluir").click()
    expect(panel).to_be_hidden()
    assert comments_of(studio, api) == []


def test_aplicar_sends_every_commented_box_with_its_comment_in_one_message_and_clears_them_when_the_turn_ends(
        studio, studio_page, api):
    page = studio_page
    panel = page.get_by_role("region", name="Comentários")
    items = panel.get_by_role("listitem")
    # the fake agent takes its scenario from a marker anywhere in the prompt, so this one comes from a comment
    add(studio, api, "mostre a figura inteira", [PIPE])
    add(studio, api, "#scenario:slow encurte", [LI9, LI8])
    page.evaluate("""() => { window.sent = new Promise((resolve) => studio.on('chat', (e) => {
        if (e.kind === 'user') resolve(e);
    })); }""")
    panel.get_by_role("button", name="Aplicar 2 comentários").click()

    user = page.evaluate("() => window.sent")
    assert [(s["slideId"], s["loc"]["line"], s["comment"]) for s in user["selection"]] == [
        ("s13", 9, "#scenario:slow encurte"), ("s13", 8, "#scenario:slow encurte"), ("s21", 79, "mostre a figura inteira")]
    expect(conversation(page).get_by_role("article", name="Você")).to_have_count(1)
    expect(items).to_have_text([re.compile("enviado"), re.compile("enviado")])
    expect(panel.get_by_role("button", name=re.compile("^Aplicar"))).to_have_count(0)

    # a comment made while the turn runs waits for the next batch
    add(studio, api, "novo", [PIPE])
    apply_one = panel.get_by_role("button", name="Aplicar 1 comentário")
    expect(apply_one).to_be_disabled()

    expect(conversation(page).get_by_role("article", name="Claude")).to_have_text(["Pronto, terminei."])
    expect(items).to_have_text([re.compile(r"^1.*s21.*novo")])
    expect(apply_one).to_be_enabled()
    assert [c["text"] for c in comments_of(studio, api)] == ["novo"]


def test_comments_of_a_turn_that_ends_with_an_error_stay_and_can_be_applied_again(studio, studio_page, api):
    page = studio_page
    panel = page.get_by_role("region", name="Comentários")
    add(studio, api, "#scenario:no-such-scenario", [LI9])  # the fake fails: no scenario file
    page.evaluate("""() => { window.states = [];
        studio.on('comments', (e) => window.states.push(e.comments.map((c) => Boolean(c.sent)))); }""")
    panel.get_by_role("button", name="Aplicar 1 comentário").click()

    expect(page.get_by_role("alert")).to_contain_text("O agente parou com um erro")
    wait_until(lambda: page.evaluate("() => window.states").count([True]) == 1
               and page.evaluate("() => window.states.at(-1)") == [False], message="the comment sent, then back")
    expect(panel.get_by_role("button", name="Aplicar 1 comentário")).to_be_enabled()
    [comment] = comments_of(studio, api)
    assert comment["text"] == "#scenario:no-such-scenario" and comment["sent"] is None


def test_comments_live_in_the_data_dir_and_a_restart_keeps_them_with_none_left_sent(api):
    kit, data = make_kit_copy(), Path(tempfile.mkdtemp(prefix="deck-studio-data-"))
    try:
        with run_studio("--data", data, kit=kit) as s:
            comment = add(s, api, "#scenario:slow encurte", [LI9])
            chat = api.post(f"{s.base}/api/chats", headers=s.headers, data={}).json()
            box = {**LI9, "comment": comment["text"], "commentId": comment["id"]}  # what "Aplicar" sends
            res = api.post(f"{s.base}/api/chats/{chat['id']}/messages", headers=s.headers,
                           data={"text": "Aplique os comentários.", "selection": [box]})
            assert res.status == 202
            wait_until(lambda: comments_of(s, api)[0]["sent"] == res.json()["turnId"], message="the comment sent")
        # the studio stopped in the middle of that turn
        with run_studio("--data", data, kit=kit) as s:
            assert [(c["id"], c["text"], c["selection"], c["sent"]) for c in comments_of(s, api)] == [
                (comment["id"], "#scenario:slow encurte", [LI9], None)]
    finally:
        remove_kit_copy(kit)
        shutil.rmtree(data, ignore_errors=True)
