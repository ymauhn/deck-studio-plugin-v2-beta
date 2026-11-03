"""Approvals: a tool call the guard asks about waits for the author's Permitir or Negar (SPEC story 34)."""
import json

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import SCENARIOS, status_of

TIMEOUT_S = 6  # the module's approval timeout (the default is 10 min)
# 439 characters on 4 lines, the riskiest part last
LONG_COMMAND = json.loads((SCENARIOS / "bash-long.json").read_text(encoding="utf-8"))["steps"][0]["input"]["command"]


@pytest.fixture(scope="module")
def studio_args(tmp_path_factory):
    config = tmp_path_factory.mktemp("cfg") / "config.json"
    config.write_text(json.dumps({"approvalTimeout": TIMEOUT_S}), encoding="utf-8")
    return ["--config", config]


def composer(page):
    return page.get_by_role("textbox", name="Mensagem")


def answers(page):
    return page.get_by_role("log", name="Conversa").get_by_role("article", name="Claude")


def send(page, text):
    composer(page).fill(text)
    composer(page).press("Enter")


def approval(page):
    return page.get_by_role("article", name="Aprovação: Bash")


def test_a_shell_command_waits_for_the_author_and_runs_after_permitir(studio, studio_page, api):
    page = studio_page
    send(page, "#scenario:bash")
    card = approval(page)
    expect(card).to_contain_text("npm run lint")
    expect(card).to_contain_text("O desfazer não cobre o que ele mudar.")
    assert status_of(studio, api)["busy"] is True

    card.get_by_role("button", name="Permitir").click()
    expect(answers(page).last).to_have_text("Resultado: (simulado: o agente de teste não roda Bash)")
    expect(card.get_by_role("status")).to_have_text("Permitido")
    expect(card.get_by_role("button")).to_have_count(0)


def test_the_card_shows_the_whole_command_every_line_so_the_author_reads_all_they_allow(studio_page):
    """The card cut a command at 200 characters (2026-10-28): the author allowed what they could not read."""
    page = studio_page
    send(page, "#scenario:bash-long")
    card = approval(page)
    expect(card).to_contain_text("rascunhos-que-ninguem-usa")  # its last characters
    assert card.locator("pre").inner_text() == LONG_COMMAND  # every character, each line on its own
    card.get_by_role("button", name="Negar").click()
    expect(answers(page).last).to_have_text("Resultado: PreToolUse:Bash hook error: Negado pelo autor.")


def test_negar_denies_the_call_and_the_agent_is_told(studio_page):
    page = studio_page
    send(page, "#scenario:bash")
    approval(page).get_by_role("button", name="Negar").click()
    expect(answers(page).last).to_have_text("Resultado: PreToolUse:Bash hook error: Negado pelo autor.")
    expect(approval(page).get_by_role("status")).to_have_text("Negado")


def test_a_pending_approval_shows_again_after_the_page_reloads(studio, studio_page):
    page = studio_page
    send(page, "#scenario:bash")
    expect(approval(page)).to_be_visible()
    page.reload()
    expect(page.locator("body[data-ready]")).to_be_attached()
    approval(page).get_by_role("button", name="Permitir").click()
    expect(answers(page).last).to_have_text("Resultado: (simulado: o agente de teste não roda Bash)")


def test_an_approval_without_an_answer_is_denied_when_its_time_runs_out(studio_page):
    page = studio_page
    send(page, "#scenario:bash")
    expect(approval(page)).to_be_visible()
    expect(answers(page).last).to_have_text(
        "Resultado: PreToolUse:Bash hook error: Negado: o autor não respondeu a tempo.", timeout=(TIMEOUT_S + 10) * 1000)
    expect(approval(page).get_by_role("status")).to_have_text("Negado: sem resposta a tempo.")


def test_an_approved_write_outside_the_allowed_area_belongs_to_the_turn(studio, studio_page):
    page = studio_page
    page.evaluate("""() => { window.turnEnd = new Promise((resolve) => {
        const off = studio.on('chat', (e) => { if (e.kind === 'turn-end') { off(); resolve(e); } });
    }); }""")
    send(page, "#scenario:write-tools")
    card = page.get_by_role("article", name="Aprovação: Write")
    expect(card).to_contain_text("tools/nota-do-agente.txt")
    expect(card).to_contain_text("fora da área liberada")
    card.get_by_role("button", name="Permitir").click()
    expect(answers(page).last).to_have_text("Escrevi a nota.")
    assert page.evaluate("() => window.turnEnd")["files"] == ["tools/nota-do-agente.txt"]
    assert (studio.kit / "tools" / "nota-do-agente.txt").read_text(encoding="utf-8") == "nota\n"


def test_stopping_the_turn_cancels_its_pending_approval(studio, studio_page, api):
    page = studio_page
    send(page, "#scenario:bash")
    expect(approval(page)).to_be_visible()
    chat_id = page.evaluate("() => studio.chat.current().id")
    assert api.post(f"{studio.base}/api/chats/{chat_id}/interrupt", headers=studio.headers).status == 200
    expect(approval(page).get_by_role("status")).to_have_text("Cancelado: o pedido parou.")
    expect(page.get_by_role("alert")).to_contain_text("Pedido interrompido.")


def test_the_approvals_route_refuses_unknown_ids_and_other_decisions(studio, api):
    post = lambda path, data: api.post(f"{studio.base}{path}", headers=studio.headers, data=data)  # noqa: E731
    assert post("/api/approvals/no-such-id", {"decision": "allow"}).status == 404
    assert post("/api/approvals/no-such-id", {"decision": "talvez"}).status == 400
