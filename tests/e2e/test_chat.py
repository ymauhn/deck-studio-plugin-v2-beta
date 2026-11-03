"""Slice 4: chat with the fake agent (scenarios in tests/fixtures/scenarios)."""
from playwright.sync_api import expect

from tests.e2e.conftest import center, deck_of, go_slide, status_of


def composer(page):
    return page.get_by_role("textbox", name="Mensagem")


def conversation(page):
    return page.get_by_role("log", name="Conversa")


def user_messages(page):
    return conversation(page).get_by_role("article", name="Você")


def answers(page):
    return conversation(page).get_by_role("article", name="Claude")


def send(page, text):
    composer(page).fill(text)
    composer(page).press("Enter")


def test_enter_sends_the_message_and_shift_enter_makes_a_new_line(studio_page):
    page = studio_page
    box = composer(page)
    box.click()
    box.press_sequentially("primeira linha")
    box.press("Shift+Enter")
    box.press_sequentially("segunda linha")
    expect(box).to_have_value("primeira linha\nsegunda linha")
    expect(user_messages(page)).to_have_count(0)

    box.press("Enter")
    expect(user_messages(page)).to_have_count(1)
    assert user_messages(page).first.inner_text() == "primeira linha\nsegunda linha"
    expect(box).to_have_value("")
    expect(answers(page).last).to_have_text("ok")  # the fake's answer without a scenario marker


def test_scenario_hello_streams_the_answer_into_a_bubble(studio_page):
    page = studio_page
    # what the studio streams for this turn, read from its own event stream
    page.evaluate("""() => new Promise((listening) => {
        window.kinds = new Promise((resolve) => {
            const seen = [];
            const events = new EventSource('/api/events');
            events.onmessage = (m) => {
                const e = JSON.parse(m.data);
                if (e.type !== 'chat' || e.kind === 'user') return;
                seen.push(e.kind);
                if (e.kind === 'turn-end') { events.close(); resolve(seen); }
            };
            events.onopen = listening;
        });
    })""")

    send(page, "#scenario:hello")
    expect(answers(page).last).to_have_text("Olá! Sou o agente de teste do Deck Studio.")
    seen = page.evaluate("() => window.kinds")
    assert seen.count("text-delta") > 1
    assert seen.index("text-delta") < seen.index("text")
    assert seen[-1] == "turn-end"


def test_the_agents_markdown_shows_as_bold_italic_code_lists_bold_headings_and_code_blocks(studio_page):
    """The chat showed the agent's Markdown raw (2026-10-28): its "**", "- " and backticks."""
    page = studio_page
    send(page, "#scenario:markdown")
    answer = answers(page).last
    expect(answer.locator("ul > li")).to_have_text(["Autor: preencha o \\author do título.",
                                                    "A Figura 5.6 ficou de fora."])
    expect(answer.locator("li strong")).to_have_text("Autor:")
    expect(answer.locator("li code")).to_have_text("\\author")
    expect(answer.locator("li em")).to_have_text("Figura 5.6")
    expect(answer.locator("ol > li")).to_have_text(["Título", "Problema"])
    expect(answer.locator("p > strong")).to_have_text(["Para revisar:", "Próximos passos"])  # a heading: a bold line
    assert answer.locator("pre").inner_text() == "\\begin{frame}{Resultados}\n  \\includegraphics{fig}"
    expect(answer.locator(":scope > p").last).to_have_text("O resto ficou como estava.")
    for raw in ("**", "`", "## ", "- "):
        expect(answer).not_to_contain_text(raw)

    page.reload()  # drawn again from the kept text
    expect(page.locator("body[data-ready]")).to_be_attached()
    expect(answers(page).last.locator("ol > li")).to_have_text(["Título", "Problema"])


def test_markup_in_an_answer_shows_as_text_and_never_runs(studio_page):
    page = studio_page
    send(page, "#scenario:markup")
    answer = answers(page).last
    expect(answer).to_contain_text("""Veja <img src="x" onerror="window.planted = 'img'"> e """
                                   "<script>window.planted = 'script'</script>, o ")
    expect(answer.locator("code")).to_have_text("""<b onclick="window.planted = 'code'">x</b>""")
    expect(answer.locator("strong")).to_have_text("<i>isto</i>")
    expect(answer.locator("img, script, b, i")).to_have_count(0)
    assert page.evaluate("() => window.planted") is None


def test_a_rate_step_updates_the_5_hour_limit_meter(studio, studio_page, api):
    page = studio_page
    send(page, "#scenario:rate")
    expect(page.get_by_text("limite de 5 h: 12%")).to_be_visible()
    expect(page.get_by_text("semana: 50%")).to_be_visible()

    assert status_of(studio, api)["usage"] == {"five_hour": 0.12, "seven_day": 0.5}
    page.reload()
    expect(page.get_by_text("limite de 5 h: 12%")).to_be_visible()


def test_a_chat_that_would_bill_the_api_key_is_refused_with_a_portuguese_error_and_no_answer(studio, studio_page, api):
    page = studio_page
    send(page, "#scenario:apikey")
    expect(page.get_by_role("alert")).to_contain_text("chave de API")
    assert status_of(studio, api)["auth"] == "refused"

    # the next message opens a fresh session; by the time it answers, the refused turn is over without an answer
    send(page, "#scenario:hello")
    expect(answers(page)).to_have_text(["Olá! Sou o agente de teste do Deck Studio."])
    expect(conversation(page)).not_to_contain_text("não deveria aparecer")
    assert status_of(studio, api)["auth"] == "ok"


def test_the_model_selector_opus_by_default_sonnet_haiku_reaches_the_agent(studio_page):
    page = studio_page
    model = page.get_by_role("combobox", name="Modelo")
    expect(model.get_by_role("option")).to_have_text(["Opus", "Sonnet", "Haiku"])
    expect(model).to_have_value("opus")

    def ask(expected):
        send(page, "#scenario:model")
        expect(answers(page).last).to_have_text(f"Modelo: {expected}")

    ask("opus")
    model.select_option(label="Sonnet")  # the chat's session is already running: the change applies to it
    ask("sonnet")
    model.select_option(label="Haiku")
    ask("haiku")
    page.reload()
    expect(model).to_have_value("haiku")


def test_the_selection_chips_go_with_the_message_and_are_cleared_after_sending(studio_page):
    page = studio_page
    page.get_by_role("button", name="Selecionar (S)").click()
    go_slide(page, 13, 3)
    page.mouse.click(*center(deck_of(page).locator('[data-loc="deck/src/slides/03-data.html:9:5"]')))
    page.keyboard.down("Shift")
    page.mouse.click(*center(deck_of(page).locator("#s13 table td").nth(6)))
    page.keyboard.up("Shift")
    chips = page.get_by_role("list", name="Seleção").get_by_role("listitem")
    expect(chips).to_have_count(2)

    send(page, "#scenario:selection")
    expect(answers(page).last).to_have_text("Seleção: s13 li 03-data.html:9, s13 div 03-data.html:5")
    expect(user_messages(page).last.get_by_role("listitem")).to_have_count(2)
    expect(chips).to_have_count(0)
    expect(deck_of(page).locator(".studio-selected:visible")).to_have_count(0)

    send(page, "#scenario:selection")
    expect(answers(page).last).to_have_text("Seleção: nenhuma")


def test_one_turn_runs_at_a_time_across_chats_a_second_send_gets_409_and_the_composer_waits_its_turn(
        studio, studio_page, api):
    page = studio_page
    send(page, "#scenario:slow")
    expect(user_messages(page)).to_have_text(["#scenario:slow"])

    def post(path, data):
        return page.request.post(f"{studio.base}{path}", headers={"Origin": studio.base}, data=data)

    other = post("/api/chats", {}).json()
    assert post(f"/api/chats/{other['id']}/messages", {"text": "oi"}).status == 409
    assert status_of(studio, api)["busy"] is True

    send(page, "#scenario:hello")
    waiting = page.get_by_role("status").filter(has_text="Aguardando")
    expect(waiting).to_be_visible()
    expect(composer(page)).to_have_value("#scenario:hello")

    # when the running turn ends, the waiting message goes out by itself
    expect(answers(page)).to_have_text(["Pronto, terminei.", "Olá! Sou o agente de teste do Deck Studio."])
    expect(waiting).to_be_hidden()
    expect(composer(page)).to_have_value("")
    assert status_of(studio, api)["busy"] is False


def test_an_agent_that_fails_shows_the_error_and_the_studio_keeps_answering(studio_page):
    page = studio_page
    send(page, "#scenario:no-such-scenario")  # the fake fails: no scenario file
    expect(page.get_by_role("alert")).to_contain_text("O agente parou com um erro")

    send(page, "#scenario:hello")
    expect(answers(page)).to_have_text(["Olá! Sou o agente de teste do Deck Studio."])


def test_studio_on_gets_the_events_the_server_publishes_and_studio_chat_send_sends_with_a_selection(studio_page):
    page = studio_page
    item = {"slideId": "s13", "slide": 13, "step": 3, "part": "03-data.html",
            "loc": {"file": "deck/src/slides/03-data.html", "line": 9, "col": 5}, "tag": "li", "kind": "text",
            "comment": "mais curto"}
    page.evaluate("""() => { window.got = new Promise((resolve) => {
        const kinds = [];
        studio.on('chat', (e) => { kinds.push(e.kind); if (e.kind === 'turn-end') resolve(kinds); });
    }); }""")
    reply = page.evaluate("(item) => studio.chat.send('#scenario:selection', { selection: [item] })", item)
    assert reply["status"] == 202 and reply["data"]["turnId"]
    assert page.evaluate("() => window.got")[-1] == "turn-end"
    expect(answers(page).last).to_have_text("Seleção: s13 li 03-data.html:9")
