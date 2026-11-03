"""Direct text edits (SPEC stories 39-43): POST /api/edit-text as an undoable turn, and editing in place in the deck."""
from playwright.sync_api import expect

from tests.e2e.conftest import deck_of, go_slide, slide_and_step, status_of, wait_until

PART = "deck/src/slides/03-data.html"  # CRLF line endings


def post(studio, api, path, data):
    return api.post(f"{studio.base}{path}", headers=studio.headers, data=data)


def edit_body(line, col, old, new, child=0):
    return {"loc": {"file": PART, "line": line, "col": col}, "childIndex": child, "oldText": old, "newText": new}


def at(page, loc):
    return deck_of(page).locator(f'[data-loc="deck/src/slides/{loc}"]')


def editor(page):
    return deck_of(page).get_by_role("textbox", name="Editar texto")


def marked(page, loc):
    """Mark the box at loc; returns the box that replaces it once the deck is rebuilt."""
    at(page, loc).evaluate("(el) => { el.dataset.old = ''; }")
    return deck_of(page).locator(f'[data-loc="deck/src/slides/{loc}"]:not([data-old])')


def test_a_direct_edit_gets_409_while_an_agent_turn_holds_the_turn_lock_and_goes_through_after_it(studio, api):
    old = "2,422,234 records, 791,011 distinct pairs, 86,423 proteins"
    new = "2,422,234 records and 791,011 distinct pairs over 86,423 proteins"
    before = (studio.kit / PART).read_bytes()
    chat = post(studio, api, "/api/chats", {}).json()
    assert post(studio, api, f"/api/chats/{chat['id']}/messages", {"text": "#scenario:slow"}).status == 202

    res = post(studio, api, "/api/edit-text", edit_body(34, 5, old, new))
    assert res.status == 409
    assert res.json()["error"] == "busy"
    assert (studio.kit / PART).read_bytes() == before

    wait_until(lambda: not status_of(studio, api)["busy"], message="the agent turn to end")
    res = post(studio, api, "/api/edit-text", edit_body(34, 5, old, new))
    assert res.status == 200
    assert res.json()["turnId"]
    assert (studio.kit / PART).read_bytes() == before.replace(old.encode(), new.encode())


def test_a_stale_edit_gets_409_generated_content_422_and_a_file_outside_the_editable_area_403(studio, api):
    before = (studio.kit / PART).read_bytes()
    thesis = studio.kit / "source" / "thesis" / "dissertation.tex"
    thesis_before = thesis.read_bytes()

    def refused(body):
        res = post(studio, api, "/api/edit-text", body)
        return res.status, res.json()["error"]

    stale = post(studio, api, "/api/edit-text", edit_body(35, 5, "Combined score in [0.400, 0.999]; old text", "x"))
    assert stale.status == 409
    assert stale.json() == {"error": "stale",
                            "message": "O texto mudou no arquivo desde a seleção. Recarregue e tente de novo."}
    assert refused(edit_body(999, 5, "x", "y")) == (409, "not-found")  # the box is gone from the source
    assert refused(edit_body(5, 5, "", "x")) == (422, "not-editable")  # the generated corpus table of s13
    assert refused(edit_body(86, 7, r"wF_{\max}", "x")) == (422, "not-editable")  # display math of s16
    assert refused(edit_body(79, 5, "", "x", child=1)) == (422, "not-text")  # the <sub> of "wF<sub>max</sub>"
    assert refused({**edit_body(1, 1, "x", "y"), "loc": {"file": "source/thesis/dissertation.tex", "line": 1, "col": 1}}) \
        == (403, "denied")
    assert refused({**edit_body(1, 1, "x", "y"), "loc": {"file": "deck/../../outside.html", "line": 1, "col": 1}}) \
        == (403, "denied")
    assert refused({"loc": {"file": PART, "line": "9"}, "oldText": "x", "newText": "y"}) == (400, "bad-edit")
    # an empty box could not be double-clicked again: removing it is a request for the chat
    assert refused(edit_body(35, 5, "Combined score in [0.400, 0.999]; confidence, not binding strength", " \n ")) \
        == (400, "empty")
    assert (studio.kit / PART).read_bytes() == before
    assert thesis.read_bytes() == thesis_before


def test_a_double_click_outside_select_mode_edits_a_plain_text_box_in_place_and_enter_saves_it_to_the_source(
        studio, studio_page):
    page = studio_page
    old, new = "Labels per protein (mean): 25.91 BP, 12.48 CC, 7.55 MF", "Mean labels per protein: BP 25.91, CC 12.48, MF 7.55"
    before = (studio.kit / PART).read_bytes()
    go_slide(page, 13, 2)
    at(page, "03-data.html:8:5").click()  # a single click on a text box still moves the deck on
    wait_until(lambda: slide_and_step(page) == (13, 3), message="the deck to go on")

    rebuilt = marked(page, "03-data.html:9:5")
    at(page, "03-data.html:9:5").dblclick()
    expect(editor(page)).to_have_text(old)
    assert slide_and_step(page) == (13, 3)  # the clicks of the double click did not move the deck
    editor(page).fill(new)
    editor(page).press("Enter")

    expect(rebuilt).to_have_text(new)
    assert (studio.kit / PART).read_bytes() == before.replace(old.encode(), new.encode())
    assert slide_and_step(page) == (13, 3)
    expect(editor(page)).to_have_count(0)


def test_esc_cancels_an_in_place_edit_and_leaves_the_source_unchanged(studio, studio_page):
    page = studio_page
    text = "Each pair repeated 3.06 times on average (up to 170), always with the same score"
    before = (studio.kit / PART).read_bytes()
    go_slide(page, 14, 2)
    at(page, "03-data.html:36:5").dblclick()
    editor(page).fill("Um texto que não fica")
    editor(page).press("Escape")

    expect(editor(page)).to_have_count(0)
    expect(at(page, "03-data.html:36:5")).to_have_text(text)
    assert slide_and_step(page) == (14, 2)
    page.wait_for_timeout(1000)  # nothing goes to the studio: no write comes later either
    assert (studio.kit / PART).read_bytes() == before


def test_a_refused_in_place_edit_shows_why_and_generated_content_does_not_open_an_editor(studio, studio_page):
    page = studio_page
    path = studio.kit / PART
    original = path.read_bytes()
    # the source changes after the deck was built, behind the studio's back
    changed = original.replace(b"no temporal or homology constraint", b"no temporal constraint")
    path.write_bytes(changed)
    try:
        go_slide(page, 13, 3)
        at(page, "03-data.html:8:5").dblclick()
        editor(page).fill("80 / 10 / 10 split at protein level")
        editor(page).press("Enter")
        expect(page.get_by_role("alert").filter(has_text="O texto mudou no arquivo desde a seleção")).to_be_visible()
        expect(editor(page)).to_have_count(0)
        expect(at(page, "03-data.html:8:5")).to_have_text(
            "80 / 10 / 10 split, disjoint at protein level, no temporal or homology constraint")
        assert path.read_bytes() == changed
    finally:
        path.write_bytes(original)

    for box in [deck_of(page).locator("#s13 table td").nth(6), deck_of(page).locator("#s13 table th").first]:
        box.dblclick()
        expect(page.get_by_role("status").filter(has_text="Conteúdo gerado")).to_have_count(1)
        expect(editor(page)).to_have_count(0)
        assert slide_and_step(page) == (13, 3)
        page.get_by_role("status").filter(has_text="Conteúdo gerado").evaluate("(el) => el.remove()")
    go_slide(page, 16, 1)
    deck_of(page).locator('#s16 [data-loc="deck/src/slides/03-data.html:86:7"]').dblclick()  # display math
    expect(page.get_by_role("status").filter(has_text="Conteúdo gerado")).to_have_count(1)
    expect(editor(page)).to_have_count(0)
    assert slide_and_step(page) == (16, 1)
