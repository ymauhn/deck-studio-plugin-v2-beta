"""Jobs (stories 50-53): Exportar PDF, Publicar and Regenerar Beamer run in the background with a live log.

The adapter's job commands are replaced through --config with harmless Python one-liners, so nothing here
runs the kit's exporter, publishes to Netlify or runs the kit's Beamer build. They run in the kit copy."""
import json
import re
import sys

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import built, run_studio, wait_until

PY = sys.executable
PDF = b"%PDF-1.4 jobs test"


def py(code):
    return [PY, "-c", code]


# outputs are printed with separate arguments, so the "> command" line that announces each command never
# contains an output line itself
JOBS = {
    "export-pdf": [py("print('clean', 'build')"),
                   py("import pathlib; d = pathlib.Path('deck', 'dist'); d.mkdir(exist_ok=True); "
                      f"(d / 'nexus-go-defense.pdf').write_bytes({PDF!r}); print('wrote', 'deck/dist/nexus-go-defense.pdf')")],
    # one "x" in published.log per run
    "publish": [py("print('clean', 'build')"),
                py("open('published.log', 'a').write('x'); print('ready:', 'https://jobs-test.netlify.app')")],
    # the first line is flushed and then the job waits: a live log shows it before the job ends
    "beamer": [py("import pathlib, time; print('pass', 1, flush=True); time.sleep(2.5); "
                  f"pathlib.Path('beamer').mkdir(exist_ok=True); pathlib.Path('beamer', 'nexus-go-defense.pdf').write_bytes({PDF!r}); "
                  "print('pass', 2)")],
    # jobs of another deck's adapter, for the failures
    "broken": [py("import sys; print('boom'); sys.exit(3)"), py("open('never.txt', 'w')")],
    "missing": [["deck-studio-no-such-program"]],
}


@pytest.fixture(scope="module")
def studio_args(tmp_path_factory):
    config = tmp_path_factory.mktemp("jobs") / "config.json"
    config.write_text(json.dumps({"jobs": JOBS}), encoding="utf-8")
    return ["--config", config]


def run_in_page(page, name, body=None):
    """POST /api/jobs/<name> from the studio page; returns {status, data, events}, the events of that job
    until its end (none when the start was refused)."""
    return page.evaluate("""async ([name, body]) => {
        const events = [];
        let ended;
        const end = new Promise((resolve) => { ended = resolve; });
        const off = studio.on('job', (e) => {
            if (e.name !== name) return;
            events.push(e);
            if (e.state !== 'running') ended();
        });
        const { status, data } = await studio.api(`/api/jobs/${name}`, body ?? {});
        if (status === 202) await end;
        off();
        return { status, data, events };
    }""", [name, body])


def outputs(lines):
    """The log lines a job's commands printed, without the "> command" lines that announce each command."""
    return [line for line in lines if not line.startswith("> ")]


def test_job_events_carry_the_job_id_name_state_and_log_lines_from_start_to_end(studio_page):
    run = run_in_page(studio_page, "export-pdf")
    assert run["status"] == 202
    events = run["events"]
    job_id = run["data"]["jobId"]
    assert events[0] == {"type": "job", "id": job_id, "name": "export-pdf", "state": "running"}
    assert {e["id"] for e in events} == {job_id}
    lines = [e["line"] for e in events[1:-1]]
    assert all(e["state"] == "running" for e in events[:-1])
    # each command is announced, then its output follows, in order
    assert [line.startswith("> ") for line in lines] == [True, False, True, False]
    assert outputs(lines) == ["clean build", "wrote deck/dist/nexus-go-defense.pdf"]
    end = events[-1]
    assert end["state"] == "ok"
    assert end["ms"] > 0
    assert end["file"] == "deck/dist/nexus-go-defense.pdf"
    assert end["url"] == "/api/jobs/files/deck/dist/nexus-go-defense.pdf"


def test_the_server_starts_publish_only_with_confirm_true_and_refuses_unknown_jobs(studio, api):
    def post(name, body):
        return api.post(f"{studio.base}/api/jobs/{name}", headers=studio.headers, data=body)

    for body in [{}, {"confirm": "yes"}, {"confirm": 1}]:
        res = post("publish", body)
        assert res.status == 400
        assert res.json()["error"] == "confirm"
    res = post("format-disk", {})
    assert res.status == 404
    assert res.json()["error"] == "not-found"


def test_a_job_runs_once_at_a_time_a_second_start_gets_409_while_another_job_may_run(studio_page):
    starts = studio_page.evaluate("""async () => {
        const ended = new Set();
        const both = new Promise((resolve) => studio.on('job', (e) => {
            if (e.state !== 'running') ended.add(e.name);
            if (ended.has('beamer') && ended.has('export-pdf')) resolve();
        }));
        const first = await studio.api('/api/jobs/beamer', {});
        const again = await studio.api('/api/jobs/beamer', {});
        const other = await studio.api('/api/jobs/export-pdf', {});
        await both;
        return [first.status, again.status, again.data.error, other.status];
    }""")
    assert starts == [202, 409, "busy", 202]


def top_button(page, label):
    return page.get_by_role("banner").get_by_role("button", name=label)


def drawer(page):
    return page.get_by_role("region", name="Tarefas")


def job_card(page, label):
    return drawer(page).get_by_role("article", name=label)


def log_outputs(card):
    return outputs(card.get_by_role("log").inner_text().splitlines())


DONE = re.compile(r"^concluído em \d+,\d s$")


def test_exportar_pdf_runs_in_the_kit_and_the_drawer_shows_its_log_the_duration_and_the_pdf_path(studio, studio_page):
    page = studio_page
    expect(drawer(page)).to_be_hidden()
    top_button(page, "Exportar PDF").click()
    card = job_card(page, "Exportar PDF")
    expect(card.get_by_role("status")).to_have_text(DONE)
    assert log_outputs(card) == ["clean build", "wrote deck/dist/nexus-go-defense.pdf"]
    expect(card).to_contain_text("PDF: deck/dist/nexus-go-defense.pdf")
    # the command wrote a relative path: the job ran in the kit root
    assert (studio.kit / "deck" / "dist" / "nexus-go-defense.pdf").read_bytes() == PDF


def test_abrir_opens_the_exported_pdf_and_the_files_route_serves_only_the_pdfs_in_deck_dist(studio, studio_page, api):
    page = studio_page
    top_button(page, "Exportar PDF").click()
    link = job_card(page, "Exportar PDF").get_by_role("link", name="Abrir")
    expect(link).to_have_attribute("href", "/api/jobs/files/deck/dist/nexus-go-defense.pdf")
    expect(link).to_have_attribute("target", "_blank")
    res = page.request.get(studio.base + link.get_attribute("href"))  # with the page's own cookie
    assert res.status == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.body() == PDF

    (studio.kit / "deck" / "dist" / "nexus-go-defense.html").write_text("<!doctype html>", encoding="utf-8")
    (studio.kit / "deck" / "secret.pdf").write_bytes(PDF)
    for path in ["deck/dist/nexus-go-defense.html", "deck/secret.pdf", "deck/dist/..%2Fsecret.pdf",
                 "deck/dist/..%5Csecret.pdf", "deck/dist/missing.pdf", "source/thesis/dissertation.tex"]:
        assert api.get(f"{studio.base}/api/jobs/files/{path}", headers=studio.headers).status == 404, path


def publish_runs(studio):
    log = studio.kit / "published.log"
    return len(log.read_text()) if log.exists() else 0


def test_publicar_asks_first_naming_the_netlify_url_and_publishes_only_after_confirmar(studio, studio_page):
    page = studio_page
    site = studio.kit / "deck" / "tools" / "netlify-site.json"
    site.unlink(missing_ok=True)  # before the first publish, the kit has no site file
    runs = publish_runs(studio)
    posts = []
    page.on("request", lambda r: posts.append(r.post_data_json)
            if r.method == "POST" and r.url.endswith("/api/jobs/publish") else None)

    top_button(page, "Publicar").click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_contain_text("Publicar o deck no Netlify?")
    dialog.get_by_role("button", name="Cancelar").click()
    expect(dialog).to_have_count(0)

    # the kit's publish script keeps the site there, written by PowerShell with a BOM
    site.write_text(json.dumps({"id": "test", "name": "jobs-test", "url": "https://jobs-test.netlify.app"}), encoding="utf-8-sig")
    top_button(page, "Publicar").click()
    expect(dialog).to_contain_text("Publicar o deck em https://jobs-test.netlify.app?")
    dialog.get_by_role("button", name="Cancelar").click()
    expect(dialog).to_have_count(0)

    top_button(page, "Publicar").click()
    dialog.get_by_role("button", name="Confirmar").click()
    expect(job_card(page, "Publicar").get_by_role("status")).to_have_text(DONE)
    assert posts == [{"confirm": True}]
    assert publish_runs(studio) == runs + 1


def test_regenerar_beamer_runs_without_asking_shows_its_log_live_and_ends_with_the_beamer_pdf_path(studio_page):
    page = studio_page
    button = top_button(page, "Regenerar Beamer")
    button.click()
    expect(page.get_by_role("dialog")).to_have_count(0)
    card = job_card(page, "Regenerar Beamer")
    # the first line is there while the job still runs
    expect(card.get_by_role("log")).to_contain_text(re.compile(r"^pass 1$", re.M))
    expect(card.get_by_role("status")).to_have_text("rodando…")
    expect(button).to_be_disabled()

    expect(card.get_by_role("status")).to_have_text(DONE)
    assert log_outputs(card) == ["pass 1", "pass 2"]
    expect(card).to_contain_text("PDF: beamer/nexus-go-defense.pdf")
    expect(card.get_by_role("link", name="Abrir")).to_have_count(0)  # only deck/dist PDFs are served
    expect(button).to_be_enabled()


FAILED = re.compile(r"^falhou após \d+,\d s$")


def test_a_failing_command_ends_its_job_as_an_error_and_the_commands_after_it_do_not_run(studio, studio_page):
    page = studio_page
    run = run_in_page(page, "broken")
    assert run["status"] == 202
    assert run["events"][-1]["state"] == "error"
    card = job_card(page, "broken")
    expect(card.get_by_role("status")).to_have_text(FAILED)
    assert log_outputs(card) == ["boom", "O comando saiu com o código 3."]
    assert not (studio.kit / "never.txt").exists()

    # a program that does not exist fails the job too, and the job can start again
    for _ in range(2):
        run = run_in_page(page, "missing")
        assert run["status"] == 202
        assert run["events"][-1]["state"] == "error"
    expect(job_card(page, "missing").get_by_role("status")).to_have_text(FAILED)


def test_fechar_hides_the_drawer_and_the_next_run_opens_it_again_with_one_card_per_job(studio_page):
    page = studio_page
    button = top_button(page, "Exportar PDF")
    button.click()
    expect(button).to_be_enabled()  # it is disabled while its job runs
    drawer(page).get_by_role("button", name="Fechar").click()
    expect(drawer(page)).to_be_hidden()

    button.click()
    expect(drawer(page)).to_be_visible()
    expect(button).to_be_enabled()
    expect(drawer(page).get_by_role("article")).to_have_count(1)  # the new run replaced the card of the last one


def test_no_job_starts_while_a_turn_may_be_changing_the_deck_and_the_buttons_wait_for_its_end(studio, studio_page):
    page = studio_page
    buttons = [top_button(page, label) for label in ["Regenerar Beamer", "Exportar PDF", "Publicar"]]
    runs = publish_runs(studio)
    assert page.evaluate("() => studio.chat.send('#scenario:slow')")["status"] == 202  # a turn of about 2 s
    for button in buttons:
        expect(button).to_be_disabled()
    for name, body in [("export-pdf", {}), ("publish", {"confirm": True}), ("beamer", {})]:
        res = page.evaluate("([name, body]) => studio.api(`/api/jobs/${name}`, body)", [name, body])
        assert (res["status"], res["data"]["error"]) == (409, "busy"), name
        assert "pedido em andamento" in res["data"]["message"]
    for button in buttons:
        expect(button).to_be_enabled()  # the turn ended
    assert publish_runs(studio) == runs


def timed(name, seconds):
    """A command that notes in builds.log, in the kit, when it starts and when it ends."""
    return py(f"import time; print('{name}', time.time(), file=open('builds.log', 'a')); time.sleep({seconds}); "
              f"print('{name}', time.time(), file=open('builds.log', 'a'))")


def test_the_clean_build_of_a_job_never_runs_at_the_same_time_as_a_studio_build(tmp_path, api):
    # both rewrite deck/build (thesis_tables.json, say): side by side, one could read the other's half-written file
    clean = timed("clean", 2)
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"cleanBuild": clean, "studioBuild": timed("studio", 0.2), "partBuild": None,
                                  "jobs": {"export-pdf": [clean]}}), encoding="utf-8")
    with run_studio("--config", config) as s:
        built(s, api)
        log = s.kit / "builds.log"
        log.unlink()  # the startup build's lines
        assert api.post(f"{s.base}/api/jobs/export-pdf", headers=s.headers, data={}).status == 202
        wait_until(lambda: log.exists(), 10, "the clean build")
        old = "Labels per protein (mean): 25.91 BP, 12.48 CC, 7.55 MF"  # a direct edit, then its studio build
        edit = {"loc": {"file": "deck/src/slides/03-data.html", "line": 9, "col": 5}, "childIndex": 0,
                "oldText": old, "newText": old.replace("(mean)", "(average)")}
        assert api.post(f"{s.base}/api/edit-text", headers=s.headers, data=edit).status == 200
        wait_until(lambda: len(log.read_text().splitlines()) == 4, 10, "both builds")
        times = {}
        for name, t in (line.split() for line in log.read_text().splitlines()):
            times.setdefault(name, []).append(float(t))
    assert times["studio"][0] >= times["clean"][1]
