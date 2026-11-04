"""The generator's tools in a project made by Deck Studio (Fase 1, 2026-11-04): run_qa builds the clean deck and runs
the project's own qa/ scripts; judge_deck asks the read-only judge and keeps its report in qa/JUIZ.md; every turn's
cost goes to the data dir's costs.jsonl; and the agent cannot change what checks it."""
import json
import tempfile
from pathlib import Path

import pytest
from playwright.sync_api import expect

from deck_studio.config import load_config
from deck_studio.core.write_guard import LEVELS, create_guard
from deck_studio.templates import fill_template
from tests.e2e.conftest import open_studio, run_studio
from tests.helpers.kit_copy import PREFIX, remove_kit_copy

TITLE = "Projeto do Gerador"


def make_project():
    kit = Path(tempfile.mkdtemp(prefix=PREFIX))  # remove_kit_copy deletes it
    fill_template(kit, {"TITLE": TITLE, "LANG": "pt-BR", "LANGUAGE": "Português (Brasil)",
                        "PDF": "context/artigo.pdf", "SLUG": "projeto-do-gerador"})
    (kit / "studio.json").write_text(json.dumps({"title": TITLE, "format": "html", "language": "pt"}), encoding="utf-8")
    return kit


@pytest.fixture(scope="module")
def project():
    kit = make_project()
    try:
        with run_studio(kit=kit) as s:
            yield s
    finally:
        remove_kit_copy(kit)


def answers(page):
    return page.get_by_role("log", name="Conversa").get_by_role("article", name="Claude")


def send(page, text):
    page.get_by_role("textbox", name="Mensagem").fill(text)
    page.get_by_role("textbox", name="Mensagem").press("Enter")


def test_the_template_brings_the_method(project):
    kit = project.kit
    skill = kit / ".claude/skills/criar-apresentacao"
    assert len(list((skill / "exemplos").glob("*.html"))) == 12
    assert (skill / "ESTILO.md").is_file() and not (skill / "padroes.html").exists()
    for rel in ["docs/STORYLINE.template.md", "docs/FACTS.template.md", "docs/FIGURES.template.md", "docs/DECISIONS.md",
                "docs/briefing.json", "qa/check_deck.py", "qa/audit_numbers.py", "qa/shoot.py", "qa/RUBRICA.md",
                ".claude/agents/juiz-de-slides.md", "deck/src/fonts.css"]:
        assert (kit / rel).is_file(), rel
    briefing = json.loads((kit / "docs/briefing.json").read_text(encoding="utf-8"))
    assert briefing["confirmado"] is False and briefing["identidade"] == "kit"
    assert "--c1" in (kit / "deck/src/deck.css").read_text(encoding="utf-8")


def test_run_qa_builds_the_clean_deck_and_runs_the_projects_audit(project, page):
    open_studio(page, project)
    send(page, "#scenario:run-qa")
    answer = answers(page).last
    expect(answer).to_contain_text("qa/audit_numbers.py (exit 0", timeout=120_000)
    expect(answer).to_contain_text("number audit: 0 unmatched")
    assert (project.kit / "deck/dist/deck.html").is_file()
    assert (project.kit / "qa/number_audit.md").is_file()


def test_judge_deck_keeps_its_report_and_every_turn_logs_its_cost(project, page):
    open_studio(page, project)
    send(page, "#scenario:judge")
    expect(answers(page).last).to_contain_text("Nenhum item bloqueante", timeout=60_000)
    assert "Nenhum item bloqueante" in (project.kit / "qa/JUIZ.md").read_text(encoding="utf-8")
    lines = [json.loads(line) for line in (project.data / "costs.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [line["kind"] for line in lines].count("turn") >= 2
    assert all("costUsd" in line and "usage" in line for line in lines)


def test_the_agent_never_changes_what_checks_it():
    kit = make_project()
    try:
        guard = create_guard(load_config(kit))
        for level in LEVELS:
            for rel in ["qa/check_deck.py", "qa/audit_numbers.py", "qa/shoot.py", "qa/RUBRICA.md",
                        ".claude/agents/juiz-de-slides.md"]:
                assert guard.check("Edit", {"file_path": str(kit / rel)}, level).behavior == "ask", (level, rel)
            assert guard.check("Write", {"file_path": str(kit / "docs/STORYLINE.md")}, level).behavior == (
                "ask" if level == "ask" else "allow")
    finally:
        remove_kit_copy(kit)
