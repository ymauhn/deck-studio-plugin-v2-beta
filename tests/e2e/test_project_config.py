"""The studio follows its deck's config (docs/IMPORT.md "Config"): a kit with a studio.json is a project made by Deck
Studio and gets generic_config, with its title, its own jobs and deck build, no Origem and system fonts. The NEXUS-GO
studio stays as it was."""
import http.server
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import pytest
from playwright.sync_api import expect

from deck_studio.templates import fill_template
from tests.e2e.conftest import (ROOT, SCENARIOS, built, deck_of, go_slide, open_studio, run_studio, safe_jobs,
                                status_of, wait_until)
from tests.helpers.kit_copy import PREFIX, remove_kit_copy

TITLE = "Relatório de Testes"


@pytest.fixture(scope="module")
def project():
    """A studio on the filled project template with a studio.json, as an imported project has."""
    kit = Path(tempfile.mkdtemp(prefix=PREFIX))  # remove_kit_copy deletes it
    try:
        fill_template(kit, {"TITLE": TITLE, "LANG": "pt-BR", "LANGUAGE": "Português (Brasil)",
                            "PDF": "context/relatorio.pdf", "SLUG": "relatorio-de-testes"})
        (kit / "studio.json").write_text(json.dumps({"title": TITLE, "format": "html", "language": "pt"}),
                                         encoding="utf-8")
        with run_studio(kit=kit) as s:
            yield s
    finally:
        remove_kit_copy(kit)


def test_a_kit_with_a_studio_json_gets_the_generic_config_and_its_own_project(project, api):
    # the jobs of the format the author chose: the Overleaf zip of the untouched Beamer template is not one of them
    assert status_of(project, api)["project"] == {
        "title": TITLE, "format": "html", "startMode": "html", "beamerStart": "beamer/apresentacao/apresentacao.tex",
        "provenance": False, "jobs": ["export-pdf"], "registerSite": True}


def test_a_beamer_project_starts_in_beamer_mode(api):
    kit = Path(tempfile.mkdtemp(prefix=PREFIX))  # only a studio.json, and a stand-in deck build
    try:
        (kit / "studio.json").write_text(json.dumps({"title": "Aula", "format": "beamer", "language": "en"}),
                                         encoding="utf-8")
        (kit / "e2e.json").write_text(json.dumps({"studioBuild": [sys.executable, "-c", "pass"]}), encoding="utf-8")
        with run_studio("--config", kit / "e2e.json", kit=kit) as s:
            project = status_of(s, api)["project"]
        assert (project["title"], project["format"], project["startMode"]) == ("Aula", "beamer", "beamer")
        assert project["beamerStart"] == "beamer/apresentacao/apresentacao.tex"
        # no Exportar PDF of the HTML deck, which the agent never writes here: the Beamer view opens the deck's PDF
        assert project["jobs"] == ["overleaf"]
    finally:
        remove_kit_copy(kit)


def test_its_deck_is_built_by_the_projects_own_deck_build_py_and_runs_in_the_studio(project, api, page):
    assert built(project, api)["ok"] is True
    assert (project.kit / "deck/build/studio/deck.html").is_file()
    open_studio(page, project)
    expect(deck_of(page).locator('section.slide[data-loc^="deck/src/slides/00-title.html:"]')).to_have_count(1)
    wait_until(lambda: page.evaluate("() => studio.deck.state()"), message="the deck's engine")


def test_its_studio_shows_the_project_title_in_the_top_bar_and_the_browser_tab(project, page):
    open_studio(page, project)
    expect(page).to_have_title(f"{TITLE} · Deck Studio")
    expect(page.get_by_role("banner")).to_contain_text(TITLE)
    expect(page.get_by_role("heading", level=1)).to_have_text("Deck Studio")


def job_buttons(page):
    return page.get_by_role("banner").locator(".jobs-bar button")


def origem(page):
    return page.get_by_role("region", name="Deck").get_by_role("button", name="Origem")


def test_its_studio_has_no_origem_button_and_one_button_per_job_of_its_own(project, page):
    open_studio(page, project)  # the features have loaded
    # no site yet: Publicar is not there, and the studio offers to register one (test_publish_site.py)
    expect(job_buttons(page)).to_have_text(["Exportar PDF", "Cadastrar link de publicação"])
    expect(origem(page)).to_have_count(0)


def test_a_deck_on_system_fonts_gets_an_empty_stylesheet_and_one_without_provenance_an_empty_index(project, api):
    fonts = api.get(f"{project.base}/ui/fonts.css", headers=project.headers)
    assert fonts.status == 200
    assert fonts.headers["content-type"].startswith("text/css")
    assert fonts.body() == b""
    index = api.get(f"{project.base}/api/provenance", headers=project.headers)
    assert (index.status, index.json()) == (200, {})


class Beacon(http.server.BaseHTTPRequestHandler):
    """Another server on this computer: it notes every request that reaches it."""
    hits = []

    def do_GET(self):
        self.hits.append(self.path)
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args):
        pass


def test_a_slide_loads_nothing_from_another_server(project, page):
    # the agent writes the slides from an imported PDF with no approval card: an image or a CSS url there must not
    # tell another server that the author opened the deck, nor carry what the agent put in its address
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Beacon)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    beacon = f"http://127.0.0.1:{server.server_port}"
    slide = project.kit / "deck/src/slides/90-beacon.html"
    slide.write_text(f'<section class="slide" id="s90"><h2 class="title">Beacon</h2><div class="bd">'
                     f'<img class="col-w" src="{beacon}/img.png?d=segredo" alt="">'
                     f'<p class="col-w" style="background-image: url({beacon}/bg.png?d=segredo)">Fundo</p>'
                     f'</div></section>\n', encoding="utf-8")
    try:
        open_studio(page, project)
        go_slide(page, 2)
        expect(deck_of(page).locator("#s90 p")).to_be_visible()
        page.wait_for_timeout(1000)
        assert Beacon.hits == []
    finally:
        slide.unlink()
        server.shutdown()
        server.server_close()


def test_a_studio_started_with_parent_pid_exits_when_that_process_ends(api):
    parent = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    try:
        with run_studio("--parent-pid", parent.pid) as s:
            built(s, api)  # no build of its own is left running
            assert status_of(s, api)["busy"] is False
            subprocess.run(["taskkill", "/F", "/PID", str(parent.pid)], capture_output=True)  # ends hard
            assert s.proc.wait(timeout=20) == 0
    finally:
        parent.kill()
        parent.wait()


@pytest.mark.parametrize("registered", [True, False])
def test_a_project_opened_by_hand_never_runs_on_the_default_kits_data_dir(tmp_path, registered):
    # python -m deck_studio --kit <project>, with no --data: NEXUS-GO's data dir (the home) would get its chats and
    # history, and the launcher would open the project instead of NEXUS-GO
    kit, local = tmp_path / "Aula de Redes", tmp_path / "localappdata"
    kit.mkdir()
    (kit / "studio.json").write_text(json.dumps({"title": "Aula de Redes", "format": "html", "language": "pt"}),
                                     encoding="utf-8")
    home = local / "deck-studio"  # the default data dir, in the LOCALAPPDATA of this test
    entry = {"name": "Aula de Redes", "slug": "aula-de-redes", "path": str(kit), "format": "html", "language": "pt",
             "created": "2026-10-28T10:00:00"}
    home.mkdir(parents=True)
    (home / "projects.json").write_text(json.dumps([entry] if registered else []), encoding="utf-8")
    config = tmp_path / "e2e.json"
    config.write_text(json.dumps({"studioBuild": [sys.executable, "-c", "pass"], **safe_jobs(kit)}), encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "deck_studio", "--kit", str(kit), "--port", "0", "--no-open", "--fake-agent",
         str(SCENARIOS), "--config", str(config)], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", env={**os.environ, "LOCALAPPDATA": str(local)})
    try:
        if registered:
            url = re.fullmatch(r"DECK_STUDIO_URL=(\S+)\n", proc.stdout.readline())[1]
            assert (home / "projects" / "aula-de-redes" / "studio.lock").read_text(encoding="utf-8") == url
        else:
            assert proc.wait(timeout=60) == 1
            assert "fora da lista de projetos" in proc.stderr.read()
        assert not (home / "studio.lock").exists()
    finally:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        proc.wait()


def test_the_nexus_go_studio_describes_its_project_in_api_status(studio, api):
    assert status_of(studio, api)["project"] == {
        "title": "NEXUS-GO", "format": "html", "startMode": "html", "beamerStart": None, "provenance": True,
        "jobs": ["export-pdf", "publish", "beamer"], "registerSite": False}


def test_the_nexus_go_studio_keeps_its_origem_button_and_its_jobs_in_their_order_and_names_its_tab(studio_page):
    page = studio_page
    expect(page).to_have_title("NEXUS-GO · Deck Studio")
    expect(page.get_by_role("heading", level=1)).to_have_text("Deck Studio")
    expect(job_buttons(page)).to_have_text(["Regenerar Beamer", "Exportar PDF", "Publicar"])
    expect(origem(page)).to_have_count(1)


def appendix_of(studio, api):
    """What the studio's agent reads after the Claude Code preset, as the fake agent says it back."""
    chat = api.post(f"{studio.base}/api/chats", headers=studio.headers, data={}).json()
    sent = api.post(f"{studio.base}/api/chats/{chat['id']}/messages", headers=studio.headers,
                    data={"text": "#scenario:appendix"})
    assert sent.status == 202

    def said():
        [c] = [c for c in api.get(f"{studio.base}/api/chats", headers=studio.headers).json() if c["id"] == chat["id"]]
        return next((m["text"] for m in c["messages"] if m["kind"] == "text"), None)
    return wait_until(said, 30, "the agent's answer")


def test_a_projects_agent_is_told_of_its_own_deck_and_not_of_nexus_go_components_and_tables(project, api):
    # the project's deck has no components (its build never loads deck/src/components) and no dissertation
    text = appendix_of(project, api)
    assert "Follow the project's CLAUDE.md and the slide rules there." in text
    assert "This deck has no components" in text
    assert "deck/src/components" not in text and "dissertation" not in text


NEXUS_GO_APPENDIX = """\
# Deck Studio

You are editing a slide deck inside Deck Studio, a local visual editor. The author sees the deck next to this chat.

- A message may start with a <selection> block: a JSON list of the boxes the author picked on the slides, each with
  its slide, source file and line (loc), tag, text and kind. That is the scope of the request: change those boxes,
  or the slides they are on, and nothing else unless asked. An item may carry a "comment" (the author's note on that
  box) or have kind "tex" (a frame of a hand-written Beamer deck: file, frame lines, line, text, page). Images of
  the selected slides follow (at most four), as the author saw them, with the selected boxes outlined in orange.
- Kinds: "component" is a runtime-rendered diagram or chart: edit the component, not its runtime DOM. "table" is
  generated from the dissertation and read-only. "math" is a formula.
- Edit only the deck sources, the context folder and the project skills. Never the dissertation sources, data/, or
  generated files (deck/dist, deck/build, beamer/slides.tex).
- Follow the deck's rules: every number comes from the dissertation or docs/FACTS.md; slide text in English, short
  bullets, no em dashes. New elements and slides use the deck's own grid, classes and components.
- An edit to the deck sources, or a shell command, rebuilds the deck by itself; if the build fails, the error comes
  back to you: fix it in the same request.
- After an edit, look at the slide with mcp__deck__screenshot_slide and run mcp__deck__check_slide; fix any
  overflow, clipping or overlap before you answer.
- Files the author dropped are in context/ (articles, notes, images). mcp__deck__add_image puts a context image in
  the deck and gives you its <img> tag. mcp__deck__get_selection returns the selection again.
- Some actions wait for the author's approval (shell commands, web access, the deck's code: deck/src/**/*.js and
  deck/src/shell.html, files outside the deck sources). Undo does not cover what a shell command changes, so prefer
  the file tools.
- The studio shows the deck under a strict CSP: a <script> or an inline handler (onclick=...) written in a slide
  never runs there. Behavior belongs in a component (deck/src/components), not in slide markup.
- Answer the author in Brazilian Portuguese, briefly.
"""


def test_the_nexus_go_agent_keeps_its_appendix_word_for_word(studio, api):
    assert appendix_of(studio, api) == NEXUS_GO_APPENDIX  # as the studio in use has it
