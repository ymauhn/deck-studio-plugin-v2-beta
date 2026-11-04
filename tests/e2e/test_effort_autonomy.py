"""Pedidos 1 and 3 (2026-11-04): the effort level next to the model, and the autonomy switch of the chat."""
import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import status_of


def composer(page):
    return page.get_by_role("textbox", name="Mensagem")


def answers(page):
    return page.get_by_role("log", name="Conversa").get_by_role("article", name="Claude")


def send(page, text):
    composer(page).fill(text)
    composer(page).press("Enter")


def switch(page):
    return page.get_by_role("radiogroup", name="Autonomia do agente")


@pytest.fixture
def level(studio, api):
    """Set the autonomy level through the switch's own route; the default comes back after the test."""
    def set_level(value):
        assert api.post(f"{studio.base}/api/settings", headers=studio.headers, data={"autonomy": value}).status == 200
    yield set_level
    set_level("deck")


# ---------- effort ----------

def test_the_effort_goes_to_the_agent_and_a_change_keeps_the_same_conversation(studio_page):
    page = studio_page
    effort = page.get_by_role("combobox", name="Esforço")
    expect(effort).to_have_value("")
    send(page, "#scenario:effort")
    expect(answers(page).last).to_contain_text("esforço: padrão")
    session = answers(page).last.inner_text().split("sessão: ")[1]

    effort.select_option("high")
    send(page, "#scenario:effort")
    expect(answers(page)).to_have_count(2)
    expect(answers(page).last).to_contain_text("esforço: high")
    assert answers(page).last.inner_text().split("sessão: ")[1] == session  # resumed, not a new conversation


def test_the_effort_is_kept_per_chat_and_the_default_of_new_chats_is_saved(studio, studio_page, api):
    page = studio_page
    page.get_by_role("button", name="Configurações").click()
    dialog = page.get_by_role("dialog", name="Configurações")
    dialog.get_by_label("Esforço dos chats novos").select_option("max")
    dialog.get_by_role("button", name="Salvar").click()
    expect(dialog).to_be_hidden()
    assert api.get(f"{studio.base}/api/settings", headers=studio.headers).json()["effort"] == "max"

    page.get_by_role("button", name="Novo chat").click()
    expect(page.get_by_role("combobox", name="Esforço")).to_have_value("max")
    send(page, "#scenario:effort")
    expect(answers(page).last).to_contain_text("esforço: max")
    chat_id = page.evaluate("() => studio.chat.current().id")
    chats = {c["id"]: c for c in api.get(f"{studio.base}/api/chats", headers=studio.headers).json()}
    assert chats[chat_id]["effort"] == "max"
    assert (studio.data / "chats" / f"{chat_id}.json").read_text(encoding="utf-8").count('"effort": "max"') == 1


def test_the_effort_route_refuses_an_unknown_level(studio, studio_page, api):
    chat_id = studio_page.evaluate("() => studio.chat.current().id")
    r = api.post(f"{studio.base}/api/chats/{chat_id}/effort", headers=studio.headers, data={"effort": "turbo"})
    assert r.status == 400


# ---------- autonomy ----------

def test_the_switch_is_visible_and_starts_at_editar_o_deck(studio_page):
    group = switch(studio_page)
    expect(group).to_be_visible()
    expect(group.get_by_role("radio")).to_have_text(["Perguntar sempre", "Editar o deck", "Autônomo"])
    expect(group.get_by_role("radio", name="Editar o deck")).to_have_attribute("aria-checked", "true")


def test_at_the_default_level_a_kit_file_is_written_without_asking(studio, studio_page):
    page = studio_page
    send(page, "#scenario:write-kit-root")
    expect(answers(page).last).to_have_text("Escrevi a nota.")
    expect(page.get_by_role("article", name="Aprovação: Write")).to_have_count(0)
    assert (studio.kit / "notas-da-defesa.md").read_text(encoding="utf-8") == "nota\n"


def test_perguntar_sempre_asks_even_for_a_slide_edit(studio, studio_page, api):
    page = studio_page
    switch(page).get_by_role("radio", name="Perguntar sempre").click()
    try:
        expect(switch(page).get_by_role("radio", name="Perguntar sempre")).to_have_attribute("aria-checked", "true")
        assert api.get(f"{studio.base}/api/settings", headers=studio.headers).json()["autonomy"] == "ask"
        send(page, "#scenario:edit-slide")
        card = page.get_by_role("article", name="Aprovação: Edit")
        expect(card).to_contain_text("perguntar sempre")
        card.get_by_role("button", name="Negar").click()
        expect(answers(page).last).to_have_text("Pronto.")
    finally:
        switch(page).get_by_role("radio", name="Editar o deck").click()
        expect(switch(page).get_by_role("radio", name="Editar o deck")).to_have_attribute("aria-checked", "true")


def test_autonomo_runs_a_local_command_but_publishing_still_asks(studio, studio_page, api, level):
    page = studio_page
    level("auto")
    page.reload()
    expect(switch(page).get_by_role("radio", name="Autônomo")).to_have_attribute("aria-checked", "true")

    send(page, "#scenario:build-local")  # the deck's own build (core/shell_policy.py); "npm run lint" now asks
    expect(answers(page).last).to_have_text("Resultado: (simulado: o agente de teste não roda Bash)")
    expect(page.get_by_role("article", name="Aprovação: Bash")).to_have_count(0)

    send(page, "#scenario:publish")
    card = page.get_by_role("article", name="Aprovação: Bash")
    expect(card).to_contain_text("publish_netlify.ps1")
    card.get_by_role("button", name="Negar").click()
    expect(answers(page).last).to_have_text("Resultado: PreToolUse:Bash hook error: Negado pelo autor.")
    assert status_of(studio, api)["busy"] is False


def test_the_settings_route_refuses_an_unknown_autonomy_level(studio, api):
    r = api.post(f"{studio.base}/api/settings", headers=studio.headers, data={"autonomy": "total"})
    assert r.status == 400
