"""Turns (SPEC stories 20, 21, 44): the diff and undo of a turn, and its card in the conversation."""
from playwright.sync_api import expect

from tests.e2e.conftest import deck_of, go_slide, slide_and_step, status_of, wait_until

PART = "deck/src/slides/03-data.html"  # CRLF line endings


def at(page, loc):
    return deck_of(page).locator(f'[data-loc="deck/src/slides/{loc}"]')


def marked(page, loc):
    """Mark the box at loc; returns the box that replaces it once the deck is rebuilt."""
    at(page, loc).evaluate("(el) => { el.dataset.old = ''; }")
    return deck_of(page).locator(f'[data-loc="deck/src/slides/{loc}"]:not([data-old])')


def cards(page):
    return page.get_by_role("log", name="Conversa").get_by_role("article", name="Alterações")


def post(studio, api, path, data=None):
    return api.post(f"{studio.base}{path}", headers=studio.headers, data=data if data is not None else {})


def edit(studio, api, line, col, old, new):
    """A direct edit of the text of the box at line:col of PART; returns its turn id."""
    body = {"loc": {"file": PART, "line": line, "col": col}, "childIndex": 0, "oldText": old, "newText": new}
    res = post(studio, api, "/api/edit-text", body)
    assert res.status == 200, res.text()
    return res.json()["turnId"]


def test_the_diff_of_a_direct_edit_is_a_unified_diff_by_kit_path_and_undo_restores_the_exact_bytes_and_rebuilds(
        studio, api):
    old, new = "Isolated: 36.65% BP, 34.95% CC, 32.19% MF", "Isolated proteins: 36.65% BP, 34.95% CC, 32.19% MF"
    before = (studio.kit / PART).read_bytes()
    turn = edit(studio, api, 55, 7, old, new)

    res = api.get(f"{studio.base}/api/turns/{turn}/diff", headers=studio.headers)
    assert res.status == 200
    diff = res.json()["diff"]
    assert diff.startswith(f"--- a/{PART}\n+++ b/{PART}\n@@ -51,9 +51,9 @@\n")
    assert f"-      <li>{old}</li>\r\n+      <li>{new}</li>\r\n" in diff

    res = post(studio, api, f"/api/turns/{turn}/undo")
    assert res.status == 200
    assert res.json() == {"restored": [PART], "removed": []}
    assert (studio.kit / PART).read_bytes() == before
    deck = api.get(f"{studio.base}/deck", headers=studio.headers).text()
    assert f"{old}</li>" in deck and new not in deck  # rebuilt before the answer

    again = post(studio, api, f"/api/turns/{turn}/undo")
    assert again.status == 409
    assert again.json()["error"] == "undone"
    assert api.get(f"{studio.base}/api/turns/no-such-turn/diff", headers=studio.headers).status == 404
    assert post(studio, api, "/api/turns/no-such-turn/undo").status == 404


def test_undo_gets_409_naming_the_file_when_a_newer_turn_changed_it_and_works_once_that_one_is_undone(studio, api):
    a, b, c = ("Stable across training, validation and test", "Stable across the training, validation and test splits",
               "Stable in every split")
    path = studio.kit / PART
    before = path.read_bytes()
    first = edit(studio, api, 56, 7, a, b)
    second = edit(studio, api, 56, 7, b, c)

    res = post(studio, api, f"/api/turns/{first}/undo")
    assert res.status == 409
    assert res.json() == {
        "error": "conflict", "conflicts": [PART],
        "message": f"Não dá para desfazer: {PART} mudou depois deste pedido. Desfaça antes as mudanças mais novas."}
    assert path.read_bytes() == before.replace(a.encode(), c.encode())

    assert post(studio, api, f"/api/turns/{second}/undo").status == 200
    assert post(studio, api, f"/api/turns/{first}/undo").status == 200
    assert path.read_bytes() == before


def test_undo_gets_409_while_an_agent_turn_holds_the_turn_lock(studio, api):
    old, new = ("Thresholds up to 0.40 are inert; at 0.90 more than half the proteins are isolated",
                "Thresholds up to 0.40 change nothing; at 0.90 more than half the proteins are isolated")
    path = studio.kit / PART
    before = path.read_bytes()
    turn = edit(studio, api, 65, 7, old, new)
    chat = post(studio, api, "/api/chats").json()
    assert post(studio, api, f"/api/chats/{chat['id']}/messages", {"text": "#scenario:slow"}).status == 202

    res = post(studio, api, f"/api/turns/{turn}/undo")
    assert res.status == 409
    assert res.json()["error"] == "busy"
    assert path.read_bytes() == before.replace(old.encode(), new.encode())

    wait_until(lambda: not status_of(studio, api)["busy"], message="the agent turn to end")
    assert post(studio, api, f"/api/turns/{turn}/undo").status == 200
    assert path.read_bytes() == before


def test_an_in_place_edit_gets_a_card_with_its_file_a_diff_toggle_and_undo_which_restores_the_source(
        studio, studio_page):
    page = studio_page
    old, new = "Degree is heavy-tailed: median 5 to 7, maximum 763 to 805", "Heavy-tailed degree: median 5 to 7, maximum 763 to 805"
    path = studio.kit / PART
    before = path.read_bytes()
    n = cards(page).count()  # the cards of this module's earlier direct edits come back with the page
    go_slide(page, 14, 3)
    rebuilt = marked(page, "03-data.html:37:5")
    at(page, "03-data.html:37:5").dblclick()
    deck_of(page).get_by_role("textbox", name="Editar texto").fill(new)
    deck_of(page).get_by_role("textbox", name="Editar texto").press("Enter")
    expect(rebuilt).to_have_text(new)

    card = cards(page).nth(n)
    expect(cards(page)).to_have_count(n + 1)
    expect(card).to_contain_text("Texto editado em 03-data.html:37")
    expect(card.get_by_role("listitem")).to_have_text([PART])
    show = card.get_by_role("button", name="Ver diff")
    expect(show).to_have_attribute("aria-expanded", "false")
    show.click()
    diff = card.locator("pre")
    expect(show).to_have_attribute("aria-expanded", "true")
    # the tags show as text: the diff is escaped, not parsed as HTML
    expect(diff).to_contain_text(f'-    <li class="f net" data-f="3">{old}</li>')
    expect(diff).to_contain_text(f'+    <li class="f net" data-f="3">{new}</li>')
    show.click()
    expect(diff).to_be_hidden()

    restored = marked(page, "03-data.html:37:5")
    card.get_by_role("button", name="Desfazer").click()
    expect(card.get_by_role("status")).to_have_text("Desfeito.")
    expect(card.get_by_role("button", name="Desfazer")).to_be_disabled()
    expect(restored).to_have_text(old)
    assert path.read_bytes() == before
    assert slide_and_step(page) == (14, 3)


def test_a_card_whose_file_changed_after_its_turn_says_why_it_cannot_undo_and_undoes_once_the_newer_turn_is_undone(
        studio, studio_page, api):
    page = studio_page
    a, b, c = ("Every design decision on validation; test read once", "Every design decision made on validation; test read once",
               "All decisions on validation; test read once")
    path = studio.kit / PART
    before = path.read_bytes()
    n = cards(page).count()  # the cards of this module's earlier direct edits come back with the page
    edit(studio, api, 122, 5, a, b)
    edit(studio, api, 122, 5, b, c)
    first, second = cards(page).nth(n), cards(page).nth(n + 1)
    expect(cards(page)).to_have_count(n + 2)

    first.get_by_role("button", name="Desfazer").click()
    expect(first.get_by_role("status")).to_have_text(
        f"Não dá para desfazer: {PART} mudou depois deste pedido. Desfaça antes as mudanças mais novas.")
    expect(first.get_by_role("button", name="Desfazer")).to_be_enabled()
    assert path.read_bytes() == before.replace(a.encode(), c.encode())

    second.get_by_role("button", name="Desfazer").click()
    expect(second.get_by_role("status")).to_have_text("Desfeito.")
    first.get_by_role("button", name="Desfazer").click()
    expect(first.get_by_role("status")).to_have_text("Desfeito.")
    assert path.read_bytes() == before


def test_an_agent_turn_that_changed_files_gets_a_card_whose_undo_restores_the_slide_and_removes_the_new_file(
        studio, studio_page):
    page = studio_page
    conversation = page.get_by_role("log", name="Conversa")
    path, note = studio.kit / PART, studio.kit / "context" / "turn-card-note.md"
    before = path.read_bytes()
    n = cards(page).count()  # the cards of this module's earlier direct edits come back with the page

    def send(text):
        page.get_by_role("textbox", name="Mensagem").fill(text)
        page.get_by_role("textbox", name="Mensagem").press("Enter")

    send("#scenario:hello")  # a turn that changed nothing gets no card
    expect(conversation.get_by_role("article", name="Claude").last).to_have_text("Olá! Sou o agente de teste do Deck Studio.")
    send("#scenario:turn-card")
    expect(conversation.get_by_role("article", name="Claude").last).to_have_text("Pronto, mudei dois arquivos.")
    card = cards(page).nth(n)
    expect(cards(page)).to_have_count(n + 1)
    expect(card).to_contain_text("Arquivos alterados")
    expect(card.get_by_role("listitem")).to_have_text([PART, "context/turn-card-note.md"])

    card.get_by_role("button", name="Ver diff").click()
    diff = card.locator("pre")
    expect(diff).to_contain_text('+    <li class="f" data-f="1">Main criterion: wF<sub>max</sub>, information-content weighted</li>')
    expect(diff).to_contain_text("--- /dev/null\n+++ b/context/turn-card-note.md\n@@ -0,0 +1 @@\n+Nota do agente de teste.\n")

    card.get_by_role("button", name="Desfazer").click()
    expect(card.get_by_role("status")).to_have_text("Desfeito.")
    assert path.read_bytes() == before
    assert not note.exists()
    expect(deck_of(page).locator("#s16")).to_contain_text("Primary criterion")


def test_the_cards_of_direct_edits_come_back_after_a_page_reload_with_their_undo_state(studio, studio_page, api):
    page = studio_page
    path = studio.kit / PART
    before = path.read_bytes()
    edit(studio, api, 9, 5, "Labels per protein (mean): 25.91 BP, 12.48 CC, 7.55 MF",
         "Mean labels per protein: 25.91 BP, 12.48 CC, 7.55 MF")
    second = edit(studio, api, 37, 5, "Degree is heavy-tailed: median 5 to 7, maximum 763 to 805",
                  "Heavy-tailed degree: median 5 to 7, maximum 763 to 805")
    assert post(studio, api, f"/api/turns/{second}/undo").status == 200
    page.reload()
    expect(page.locator("body[data-ready]")).to_be_attached()
    kept = cards(page).filter(has_text="Texto editado em 03-data.html:9").last
    undone = cards(page).filter(has_text="Texto editado em 03-data.html:37").last
    expect(undone.get_by_role("status")).to_have_text("Desfeito.")
    expect(undone.get_by_role("button", name="Desfazer")).to_be_disabled()
    expect(kept.get_by_role("listitem")).to_have_text([PART])
    kept.get_by_role("button", name="Desfazer").click()
    expect(kept.get_by_role("status")).to_have_text("Desfeito.")
    wait_until(lambda: path.read_bytes() == before, message="the source restored")
