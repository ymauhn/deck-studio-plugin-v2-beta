"""Chats in tabs (SPEC stories 22-26): each tab is its own chat and session, with its own model and conversation."""
import json
import re

from playwright.sync_api import expect

from tests.e2e.conftest import open_studio, run_studio, status_of, wait_until


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


def tabs(page):
    return page.get_by_role("tablist", name="Chats").get_by_role("tab")


def tab(page, name):
    return page.get_by_role("tablist", name="Chats").get_by_role("tab", name=name, exact=True)


def current_tab(page):
    """The selected tab, pinned by its name."""
    return tab(page, page.get_by_role("tab", selected=True).inner_text())


def new_chat(page):
    """Open a new chat tab; returns that tab."""
    n = tabs(page).count()
    page.get_by_role("button", name="Novo chat").click()
    expect(tabs(page)).to_have_count(n + 1)
    return tab(page, tabs(page).last.inner_text())


def test_a_new_chat_opens_in_its_own_tab_and_each_tab_shows_its_own_conversation(studio_page):
    page = studio_page
    first = current_tab(page)
    send(page, "#scenario:hello")
    expect(answers(page)).to_have_text(["Olá! Sou o agente de teste do Deck Studio."])

    second = new_chat(page)
    expect(second).to_have_attribute("aria-selected", "true")
    expect(first).to_have_attribute("aria-selected", "false")
    expect(user_messages(page)).to_have_count(0)
    send(page, "#scenario:model")
    expect(answers(page)).to_have_text(["Modelo: opus"])

    first.click()
    expect(first).to_have_attribute("aria-selected", "true")
    expect(answers(page)).to_have_text(["Olá! Sou o agente de teste do Deck Studio."])
    second.click()
    expect(answers(page)).to_have_text(["Modelo: opus"])


def test_a_tab_is_renamed_in_place_and_a_reload_brings_back_the_same_tab_and_its_conversation(studio_page):
    page = studio_page
    current_tab(page).dblclick()
    name = page.get_by_role("textbox", name="Nome do chat")
    expect(name).to_be_focused()
    name.fill("não fica")
    name.press("Escape")
    expect(name).to_have_count(0)
    expect(page.get_by_role("tab", selected=True)).not_to_have_text("não fica")

    page.get_by_role("button", name="Renomear chat").click()
    name.fill("Revisão do S13")
    name.press("Enter")
    renamed = tab(page, "Revisão do S13")
    expect(renamed).to_have_attribute("aria-selected", "true")
    send(page, "#scenario:hello")
    expect(answers(page)).to_have_text(["Olá! Sou o agente de teste do Deck Studio."])

    page.reload()
    expect(page.locator("body[data-ready]")).to_be_attached()
    expect(renamed).to_have_attribute("aria-selected", "true")
    expect(user_messages(page)).to_have_text(["#scenario:hello"])
    expect(answers(page)).to_have_text(["Olá! Sou o agente de teste do Deck Studio."])


def test_closing_a_tab_asks_first_when_it_has_messages_and_the_next_tab_takes_its_place(studio, studio_page, api):
    page = studio_page
    empty = new_chat(page)
    page.get_by_role("button", name="Fechar chat").click()  # nothing to lose: no question
    expect(empty).to_have_count(0)

    kept = current_tab(page)
    doomed = new_chat(page)
    title = doomed.inner_text()
    send(page, "#scenario:hello")
    expect(answers(page)).to_have_count(1)
    page.get_by_role("button", name="Fechar chat").click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_contain_text(f'Fechar o chat "{title}"?')
    dialog.get_by_role("button", name="Cancelar").click()
    expect(doomed).to_have_attribute("aria-selected", "true")

    page.get_by_role("button", name="Fechar chat").click()
    page.get_by_role("dialog").get_by_role("button", name="Confirmar").click()
    expect(doomed).to_have_count(0)
    expect(kept).to_have_attribute("aria-selected", "true")
    titles = [c["title"] for c in api.get(f"{studio.base}/api/chats", headers=studio.headers).json()]
    assert title not in titles and kept.inner_text() in titles


def test_each_chat_keeps_its_own_model_and_the_selector_follows_the_tab(studio_page):
    page = studio_page
    model = page.get_by_role("combobox", name="Modelo")
    first = current_tab(page)
    model.select_option(label="Haiku")
    second = new_chat(page)
    expect(model).to_have_value("opus")
    send(page, "#scenario:model")
    expect(answers(page)).to_have_text(["Modelo: opus"])

    first.click()
    expect(model).to_have_value("haiku")
    send(page, "#scenario:model")
    expect(answers(page).last).to_have_text("Modelo: haiku")
    second.click()
    expect(model).to_have_value("opus")


def test_a_turn_writes_into_its_own_chat_and_its_cards_while_another_tab_is_shown(studio, studio_page, api):
    page = studio_page
    first = current_tab(page)
    send(page, "#scenario:edit-later")
    expect(user_messages(page)).to_have_count(1)
    new_chat(page)
    wait_until(lambda: not status_of(studio, api)["busy"], 30, "the turn of the first chat")
    expect(conversation(page).get_by_role("article")).to_have_count(0)

    first.click()
    expect(answers(page)).to_have_text(["Editei o slide em segundo plano."])
    expect(conversation(page).get_by_role("article", name=re.compile(r"^Ferramenta: Editou 03-data\.html"))).to_be_visible()
    changes = conversation(page).get_by_role("article", name="Alterações")
    expect(changes.get_by_role("listitem")).to_have_text(["deck/src/slides/03-data.html"])


def test_stop_ends_the_running_turn_the_files_it_changed_stay_and_undo_still_works(studio, studio_page, api):
    page = studio_page
    part = studio.kit / "deck/src/slides/03-data.html"
    before = part.read_bytes()
    stop = page.get_by_role("button", name="Parar")
    expect(stop).to_be_hidden()
    send(page, "#scenario:edit-stop")
    expect(answers(page)).to_have_text(["Editei as notas e vou continuar."])

    page.reload()  # a page opened while the turn runs can stop it too
    expect(page.locator("body[data-ready]")).to_be_attached()
    expect(answers(page)).to_have_text(["Editei as notas e vou continuar."])
    stop.click()
    expect(page.get_by_role("alert")).to_have_text(
        "Pedido interrompido. Ficaram alterados: deck/src/slides/03-data.html.")
    expect(stop).to_be_hidden()
    assert status_of(studio, api)["busy"] is False
    assert "The CAFA5 test labels" in part.read_text(encoding="utf-8")
    expect(conversation(page)).not_to_contain_text("não deveria aparecer")

    changes = conversation(page).get_by_role("article", name="Alterações")
    changes.get_by_role("button", name="Desfazer").click()
    expect(changes.get_by_role("status")).to_have_text("Desfeito.")
    assert part.read_bytes() == before


def test_the_chats_come_back_after_a_restart_and_the_next_message_resumes_its_sdk_session(page, kit_copy, tmp_path):
    data = tmp_path / "data"  # both runs share the app data, as the author's studio does
    with run_studio("--data", data, kit=kit_copy) as studio:
        open_studio(page, studio)
        send(page, "#scenario:session")
        expect(answers(page)).to_have_count(1)
        session = re.fullmatch(r"Sessão: (\S+)", answers(page).first.inner_text())[1]
        page.get_by_role("button", name="Renomear chat").click()
        page.get_by_role("textbox", name="Nome do chat").fill("Tese")
        page.get_by_role("textbox", name="Nome do chat").press("Enter")
        expect(tab(page, "Tese")).to_be_visible()
        page.get_by_role("combobox", name="Modelo").select_option(label="Sonnet")
        new_chat(page)
        send(page, "#scenario:hello")
        expect(answers(page)).to_have_count(1)

    with run_studio("--data", data, kit=kit_copy) as studio:
        open_studio(page, studio)
        expect(tabs(page)).to_have_text(["Tese", "Chat 1"])  # numbered after the chats named "Chat <n>"
        expect(tab(page, "Chat 1")).to_have_attribute("aria-selected", "true")  # the chat used last
        expect(answers(page)).to_have_text(["Olá! Sou o agente de teste do Deck Studio."])

        tab(page, "Tese").click()
        expect(page.get_by_role("combobox", name="Modelo")).to_have_value("sonnet")
        expect(user_messages(page)).to_have_text(["#scenario:session"])
        send(page, "#scenario:session")
        expect(answers(page)).to_have_text([f"Sessão: {session}", f"Sessão: {session}"])


def test_a_chat_whose_sdk_session_is_gone_goes_on_in_a_new_session_and_says_the_old_context_is_lost(page, kit_copy,
                                                                                                    tmp_path):
    # a chat from weeks ago: the CLI swept its transcript, so its session cannot be resumed (the fake's "gone-")
    data = tmp_path / "data"
    (data / "chats").mkdir(parents=True)
    old = {"id": "old", "title": "Antigo", "model": "opus", "sessionId": "gone-0b6f6a39", "created": 1, "updated": 1,
           "messages": []}
    (data / "chats" / "old.json").write_text(json.dumps(old), encoding="utf-8")
    with run_studio("--data", data, kit=kit_copy) as studio:
        open_studio(page, studio)
        expect(tab(page, "Antigo")).to_have_attribute("aria-selected", "true")
        send(page, "#scenario:session")
        expect(answers(page)).to_have_count(1)
        session = re.fullmatch(r"Sessão: (\S+)", answers(page).first.inner_text())[1]
        assert not session.startswith("gone-")
        expect(conversation(page).get_by_role("article", name="Aviso")).to_contain_text(
            "O Claude Code não tem mais a sessão anterior deste chat")
        expect(conversation(page).get_by_role("alert")).to_have_count(0)

        send(page, "#scenario:session")  # the new session goes on
        expect(answers(page)).to_have_text([f"Sessão: {session}", f"Sessão: {session}"])
        assert json.loads((data / "chats" / "old.json").read_text(encoding="utf-8"))["sessionId"] == session
        page.reload()  # the notice is part of the conversation
        expect(conversation(page).get_by_role("article", name="Aviso")).to_have_count(1)
