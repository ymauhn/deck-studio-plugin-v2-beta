"""[drag]: moving and resizing boxes on the deck's 12-column grid, written to the source as undoable edits."""
from playwright.sync_api import expect

from tests.e2e.conftest import center, deck_of, go_slide, slide_and_step, status_of, wait_until

PART = "deck/src/slides/03-data.html"  # CRLF line endings


def post(studio, api, path, data=None):
    return api.post(f"{studio.base}{path}", headers=studio.headers, data=data if data is not None else {})


def move(line, col, tag, **change):
    """A /api/drag/apply body for the box at line:col of PART."""
    return {"loc": {"file": PART, "line": line, "col": col}, "tag": tag, **change}


def at(page, loc):
    return deck_of(page).locator(f'[data-loc="deck/src/slides/{loc}"]')


def marked(page, loc):
    """Mark the box at loc; returns the box that replaces it once the deck is rebuilt."""
    at(page, loc).evaluate("(el) => { el.dataset.old = ''; }")
    return deck_of(page).locator(f'[data-loc="deck/src/slides/{loc}"]:not([data-old])')


def handle(page, direction):
    """Moveable's resize handle on the e (right) or w (left) edge of the box it holds."""
    return deck_of(page).locator(f'.moveable-control[data-direction="{direction}"]')


def expect_handles_on(page, box, directions=("w", "e")):
    """The handles sit on the middle of the box's left (w) and right (e) edges; a box out of the grid has e only."""
    b = box.bounding_box()
    for direction, x in (("w", b["x"]), ("e", b["x"] + b["width"])):
        if direction not in directions:
            expect(handle(page, direction)).to_have_count(0)
            continue
        expect(handle(page, direction)).to_be_visible()
        hx, hy = center(handle(page, direction))
        assert abs(hx - x) < 2 and abs(hy - (b["y"] + b["height"] / 2)) < 2, (direction, hx, hy, b)


def chips(page):
    return page.get_by_role("list", name="Seleção").get_by_role("listitem")


def test_a_drag_writes_only_the_changed_layout_to_the_source_and_its_turn_undoes_it(studio, api):
    part = studio.kit / PART
    before = part.read_bytes()

    res = post(studio, api, "/api/drag/apply", move(7, 3, "ul", style={"grid-column": "6 / 13"}))  # s13's bullets
    assert res.status == 200, res.text()
    assert part.read_bytes() == before.replace(b'<ul class="b" style="grid-column: 8 / 13">',
                                               b'<ul class="b" style="grid-column: 6 / 13">')

    assert post(studio, api, f"/api/turns/{res.json()['turnId']}/undo").status == 200
    assert part.read_bytes() == before


def test_a_drag_swaps_a_grid_class_and_adds_and_removes_style_declarations(studio, api):
    part = studio.kit / PART
    before = part.read_bytes()

    def drag(body):
        assert post(studio, api, "/api/drag/apply", body).status == 200

    drag(move(78, 3, "ul", classes={"add": ["col-b"], "remove": ["col-a"]}))  # s16's bullets, class="b col-a"
    assert part.read_bytes() == before.replace(b'<ul class="b col-a">', b'<ul class="b col-b">')
    drag(move(78, 3, "ul", classes={"add": ["col-a"], "remove": ["col-b"]}))
    assert part.read_bytes() == before

    li = b'<li class="f" data-f="3">Predictions made'  # 03-data.html:81:5, no style attribute yet
    drag(move(81, 5, "li", style={"translate": "0 24px"}))
    assert part.read_bytes() == before.replace(li, b'<li class="f" data-f="3" style="translate: 0 24px">Predictions made')
    drag(move(81, 5, "li", style={"translate": None}))
    assert part.read_bytes() == before

    stack = b'<div class="col-b stack" style="gap:30px">'  # 03-data.html:84:3
    drag(move(84, 3, "div", style={"translate": "0 -16px", "width": "640px"}))
    assert part.read_bytes() == before.replace(stack, b'<div class="col-b stack" style="gap:30px; translate: 0 -16px; width: 640px">')
    drag(move(84, 3, "div", style={"translate": None, "width": None}))
    assert part.read_bytes() == before


def test_a_drag_is_refused_on_generated_boxes_stale_locations_bad_values_and_while_a_turn_runs(studio, api):
    files = [studio.kit / PART, studio.kit / "deck/src/slides/04-method.html", studio.kit / "source/thesis/dissertation.tex"]
    before = [f.read_bytes() for f in files]

    def refused(body):
        res = post(studio, api, "/api/drag/apply", body)
        return res.status, res.json()["error"]

    right = {"style": {"translate": "0 8px"}}
    assert refused(move(5, 5, "div", **right)) == (422, "not-editable")  # s13's generated corpus table
    assert refused(move(86, 7, "div", **right)) == (422, "not-editable")  # display math of s16
    assert refused({**move(80, 5, "img", **right), "loc": {"file": "deck/src/slides/04-method.html", "line": 80, "col": 5}}) \
        == (422, "not-editable")  # the figure inside the INT-PIPE component
    assert refused(move(7, 3, "div", **right)) == (409, "stale")  # another box starts there now
    assert refused(move(999, 1, "ul", **right)) == (409, "not-found")
    assert refused(move(7, 3, "ul", style={"grid-column": "8 / 13"})) == (400, "no-change")  # where it already is
    assert refused({**move(1, 1, "x", **right), "loc": {"file": "source/thesis/dissertation.tex", "line": 1, "col": 1}}) \
        == (403, "denied")
    for bad in [{"style": {"color": "red"}}, {"style": {"grid-column": "1 / 8; color: red"}},
                {"style": {"translate": '0 8px" onclick="x'}}, {"style": {"width": "auto"}}, {"style": ["translate"]},
                {"classes": {"add": ['col-b" onclick="x']}}, {"classes": {"remove": "col-a"}}]:
        assert refused(move(7, 3, "ul", **bad)) == (400, "bad-drag"), bad
    assert refused({"loc": {"file": PART, "line": "7", "col": 3}, "tag": "ul", **right}) == (400, "bad-drag")

    chat = post(studio, api, "/api/chats").json()
    assert post(studio, api, f"/api/chats/{chat['id']}/messages", {"text": "#scenario:slow"}).status == 202
    assert refused(move(7, 3, "ul", **right)) == (409, "busy")
    wait_until(lambda: not status_of(studio, api)["busy"], message="the agent turn to end")
    assert [f.read_bytes() for f in files] == before


def test_mover_puts_handles_on_the_selected_box_and_a_click_picks_its_grid_column_box(studio_page):
    page = studio_page
    select, mover = page.get_by_role("button", name="Selecionar (S)"), page.get_by_role("button", name="Mover (M)")
    expect(mover).to_have_attribute("aria-pressed", "false")
    go_slide(page, 17, 3)
    bullets = at(page, "03-data.html:120:3")  # s17's bullets, in grid columns 8 / 13
    bullet = at(page, "03-data.html:122:5")
    select.click()
    page.mouse.click(*center(bullet))
    expect(chips(page)).to_have_text(["s17 li 03-data.html:122"])

    deck_of(page).locator("body").press("m")  # the deck has the focus
    expect(mover).to_have_attribute("aria-pressed", "true")
    expect(select).to_have_attribute("aria-pressed", "false")  # the picker would take every click
    expect_handles_on(page, bullet, ["e"])  # out of the grid: a width, to the right

    page.mouse.click(*center(bullet))  # a click takes the box in the grid
    expect(chips(page)).to_have_text(["s17 ul 03-data.html:120"])
    expect_handles_on(page, bullets)
    page.mouse.dblclick(*center(bullet))  # a double click, the box under the pointer
    expect(chips(page)).to_have_text(["s17 li 03-data.html:122"])
    expect_handles_on(page, bullet, ["e"])
    assert slide_and_step(page) == (17, 3)  # the deck saw no click
    page.evaluate("() => studio.deck.reload()")  # a reloaded deck gets the mode and the handles back
    expect_handles_on(page, bullet, ["e"])

    mover.click()
    expect(mover).to_have_attribute("aria-pressed", "false")
    expect(handle(page, "e")).to_be_hidden()
    mover.press("m")  # studio page, focus on a button
    expect(mover).to_have_attribute("aria-pressed", "true")
    expect_handles_on(page, bullet, ["e"])
    select.click()  # select mode takes the pointer back
    expect(mover).to_have_attribute("aria-pressed", "false")
    expect(handle(page, "e")).to_be_hidden()


def slide_scale(page, slide_id):
    """Screen px per slide px (the deck scales its 1600 x 900 canvas to the frame)."""
    return deck_of(page).locator(f"#{slide_id}").bounding_box()["width"] / 1600


PITCH = (1600 - 2 * 88 + 32) / 12  # one grid column and its gap, in slide px (deck.css: 88 px margins, 32 px gaps)


def only_in(source, slide_id, old, new):
    """source with old replaced by new once, in the slide with that id (slides repeat start tags)."""
    head, tail = source.split(f'id="{slide_id}"'.encode())
    return head + f'id="{slide_id}"'.encode() + tail.replace(old, new, 1)


def drag_by(page, x, y, dx, dy):
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + dx / 2, y + dy / 2, steps=4)
    page.mouse.move(x + dx, y + dy, steps=4)
    page.mouse.up()


def test_dragging_a_grid_box_snaps_it_to_the_columns_writes_the_source_and_swaps_the_slide_in_place(studio, studio_page):
    page = studio_page
    part = studio.kit / PART
    before = part.read_bytes()
    go_slide(page, 17, 3)
    deck_of(page).locator("html").evaluate("() => { window.marker = 'no reload'; }")
    page.get_by_role("button", name="Mover (M)").click()
    bullet = at(page, "03-data.html:122:5")
    page.mouse.click(*center(bullet))  # the bullets of s17, grid columns 8 / 13
    rebuilt = marked(page, "03-data.html:120:3")
    expect_handles_on(page, at(page, "03-data.html:120:3"))

    k = slide_scale(page, "s17")
    drag_by(page, *center(bullet), -1.4 * PITCH * k, 3 * k)  # a column and a bit to the left, a little down

    expect(rebuilt).to_have_attribute("style", "grid-column: 7 / 12")
    assert part.read_bytes() == only_in(before, "s17", b'<ul class="b sm" style="grid-column: 8 / 13">',
                                        b'<ul class="b sm" style="grid-column: 7 / 12">')
    assert deck_of(page).locator("html").evaluate("() => window.marker") == "no reload"  # swapped in place
    assert slide_and_step(page) == (17, 3)
    expect_handles_on(page, rebuilt)
    # the module's earlier drags have cards too when this test runs after them (a page draws them on load)
    cards = page.get_by_role("log", name="Conversa").get_by_role("article", name="Alterações")
    expect(cards.filter(has_text="Caixa movida em 03-data.html:120")).to_have_count(1)


def test_resizing_snaps_an_edge_to_a_column_edge_and_a_vertical_drag_to_8_px_steps(studio, studio_page):
    page = studio_page
    part = studio.kit / PART
    before = part.read_bytes()
    go_slide(page, 14, 3)
    page.get_by_role("button", name="Mover (M)").click()
    figure, bullets = at(page, "03-data.html:26:3"), at(page, "03-data.html:33:3")  # s14: columns 1 / 8 and 8 / 13
    page.mouse.click(*center(at(page, "03-data.html:29:7")))  # the figure's caption: its grid column box is the figure
    expect_handles_on(page, figure)
    k = slide_scale(page, "s14")

    resized = marked(page, "03-data.html:26:3")
    drag_by(page, *center(handle(page, "e")), -0.7 * PITCH * k, 0)  # the right edge, most of a column to the left
    expect(resized).to_have_attribute("style", "grid-column: 1 / 7")
    figure_done = only_in(before, "s14", b'<figure class="f" data-f="1" style="grid-column: 1 / 8">',
                          b'<figure class="f" data-f="1" style="grid-column: 1 / 7">')
    assert part.read_bytes() == figure_done
    expect_handles_on(page, resized)

    page.mouse.click(*center(at(page, "03-data.html:34:5")))  # a bullet: its grid column box is the list
    expect_handles_on(page, bullets)
    moved = marked(page, "03-data.html:33:3")
    drag_by(page, *center(at(page, "03-data.html:34:5")), 0.3 * PITCH * k, 23 * k)  # 23 px down: 3 steps of 8
    expect(moved).to_have_attribute("style", "grid-column: 8 / 13; translate: 0 24px")
    assert part.read_bytes() == only_in(figure_done, "s14", b'<ul class="b sm" style="grid-column: 8 / 13">',
                                        b'<ul class="b sm" style="grid-column: 8 / 13; translate: 0 24px">')
    cards = page.get_by_role("log", name="Conversa").get_by_role("article", name="Alterações")
    expect(cards.filter(has_text="Caixa redimensionada em 03-data.html:26")).to_have_count(1)
    expect(cards.filter(has_text="Caixa movida em 03-data.html:33")).to_have_count(1)


def test_a_box_that_fits_a_deck_grid_class_gets_the_class_and_a_box_out_of_the_grid_gets_a_width_and_an_offset(
        studio, studio_page):
    page = studio_page
    part = studio.kit / "deck/src/slides/01-motivation.html"  # LF line endings
    before = part.read_bytes()
    go_slide(page, 3, 3)
    page.get_by_role("button", name="Mover (M)").click()
    bullets = deck_of(page).locator('[data-loc="deck/src/slides/01-motivation.html:4:3"]')  # class="b col-a": 1 / 6
    bullet = deck_of(page).locator('[data-loc="deck/src/slides/01-motivation.html:5:5"]')
    page.mouse.click(*center(bullet))
    expect_handles_on(page, bullets)
    k = slide_scale(page, "s03")
    drag_by(page, *center(handle(page, "e")), 6.8 * PITCH * k, 0)  # to the last column: col-w is 1 / 13
    expect(deck_of(page).locator('[data-loc="deck/src/slides/01-motivation.html:4:3"].col-w')).to_have_count(1)
    wide = only_in(before, "s03", b'<ul class="b col-a">', b'<ul class="b col-w">')
    assert part.read_bytes() == wide

    page.mouse.dblclick(*center(bullet))  # the bullet itself: out of the grid
    expect_handles_on(page, bullet, ["e"])
    li = b'<li class="f" data-f="1">Proteins take part'
    drag_by(page, *center(handle(page, "e")), -809 * k, 0)  # 1424 px wide now: 615 px, to the 8 px step 616
    styled = '[data-loc="deck/src/slides/01-motivation.html:5:5"][style="{}"]'  # the rebuilt bullet, not its preview
    expect(deck_of(page).locator(styled.format("width: 616px"))).to_have_count(1)
    assert part.read_bytes() == wide.replace(li, b'<li class="f" data-f="1" style="width: 616px">Proteins take part')
    drag_by(page, *center(bullet), 23 * k, -15 * k)  # to the 8 px step: 24 right, 16 up
    expect(deck_of(page).locator(styled.format("width: 616px; translate: 24px -16px"))).to_have_count(1)
    assert part.read_bytes() == wide.replace(
        li, b'<li class="f" data-f="1" style="width: 616px; translate: 24px -16px">Proteins take part')


def test_mover_refuses_tables_and_math_with_a_short_reason_and_a_refused_drag_puts_the_box_back(studio, api, studio_page):
    page = studio_page
    go_slide(page, 13, 1)
    page.get_by_role("button", name="Mover (M)").click()
    table = deck_of(page).locator("#s13 table td").nth(6)
    page.mouse.dblclick(*center(table))  # the table itself
    expect(page.get_by_role("status").filter(has_text="Tabela gerada")).to_have_count(1)
    # hidden, not gone: the double click's first click may have put handles on the box around it before the refusal
    expect(handle(page, "e")).to_be_hidden()
    page.mouse.click(*center(table))  # the box around it, in the grid, moves
    expect_handles_on(page, at(page, "03-data.html:4:3"))

    go_slide(page, 16, 1)
    math = at(page, "03-data.html:86:7")
    page.mouse.dblclick(*center(math))  # display math
    expect(page.get_by_role("status").filter(has_text="Fórmula gerada")).to_have_count(1)
    expect(handle(page, "e")).to_be_hidden()
    assert slide_and_step(page) == (16, 1)

    page.mouse.click(*center(math))  # its grid column box: class="col-b stack" style="gap:30px"
    stack = at(page, "03-data.html:84:3")
    expect_handles_on(page, stack)
    before = (studio.kit / PART).read_bytes()
    chat = post(studio, api, "/api/chats").json()
    assert post(studio, api, f"/api/chats/{chat['id']}/messages", {"text": "#scenario:slow"}).status == 202
    drag_by(page, *center(math), 0, 23 * slide_scale(page, "s16"))
    expect(page.get_by_role("alert").filter(has_text="Outro pedido está em andamento")).to_be_visible()
    expect(stack).to_have_attribute("style", "gap:30px")  # back where the source has it
    expect_handles_on(page, stack)
    assert (studio.kit / PART).read_bytes() == before
    wait_until(lambda: not status_of(studio, api)["busy"], message="the agent turn to end")
