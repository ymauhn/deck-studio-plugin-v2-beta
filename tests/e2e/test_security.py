"""Slice 1: launch and security (SPEC "HTTP contract": token, cookie, Host and Origin checks)."""
import http.client
import json
import re
import subprocess
import sys
from urllib.parse import urlsplit

from playwright.sync_api import expect

from deck_studio.core import plataforma
from tests.e2e.conftest import ROOT, SCENARIOS, built, go_slide, open_studio, run_studio, slide_and_step


def test_the_launch_url_sets_an_httponly_samesite_strict_cookie_and_redirects_to_root(studio, page):
    res = page.request.get(studio.url, max_redirects=0)
    assert res.status == 302
    assert res.headers["location"] == "/"
    assert re.search("HttpOnly", res.headers["set-cookie"], re.I)
    assert re.search("SameSite=Strict", res.headers["set-cookie"], re.I)

    page.goto(studio.url)
    assert page.url == f"{studio.base}/"
    cookies = page.context.cookies()
    assert [(c["value"], c["httpOnly"], c["sameSite"]) for c in cookies] == [(studio.token, True, "Strict")]


def test_the_page_shows_deck_studio_with_three_panes_arquivos_the_deck_chat(studio, page):
    page.goto(studio.url)
    expect(page.get_by_role("heading", level=1)).to_have_text("Deck Studio")
    expect(page.get_by_role("region", name="Arquivos")).to_be_visible()
    expect(page.get_by_role("region", name="Deck").locator("iframe")).to_be_visible()
    expect(page.get_by_role("region", name="Chat")).to_be_visible()


def test_api_status_without_the_token_returns_401(studio, api):
    assert api.get(f"{studio.base}/api/status").status == 401
    assert api.get(f"{studio.base}/").status == 401
    assert api.get(f"{studio.base}/api/status", headers={"x-studio-token": "wrong"}).status == 401
    assert api.get(f"{studio.base}/api/status", headers=studio.headers).status == 200


def status_with_host(studio, host):
    """Raw request, so the Host header goes out exactly as given."""
    u = urlsplit(studio.base)
    conn = http.client.HTTPConnection(u.hostname, u.port, timeout=10)
    try:
        conn.request("GET", "/api/status", headers={"Host": host, **studio.headers})
        return conn.getresponse().status
    finally:
        conn.close()


def test_a_wrong_host_header_returns_403(studio):
    port = urlsplit(studio.base).port
    assert status_with_host(studio, f"evil.example:{port}") == 403
    assert status_with_host(studio, f"127.0.0.1.nip.io:{port}") == 403
    assert status_with_host(studio, f"127.0.0.1:{port + 1}") == 403
    assert status_with_host(studio, f"127.0.0.1:{port}") == 200
    assert status_with_host(studio, f"localhost:{port}") == 200


def test_a_post_with_a_foreign_origin_returns_403_even_with_the_cookie(studio, page):
    page.goto(studio.url)  # the page's request context now carries the studio cookie
    port = urlsplit(studio.base).port

    def post(headers):
        return page.request.post(f"{studio.base}/api/chats", headers=headers, data={})

    assert post({"Origin": "http://evil.example"}).status == 403
    assert post({"Origin": f"http://127.0.0.1:{port + 1}"}).status == 403
    assert post({}).status == 403
    assert post({"Origin": studio.base}).ok
    # header-token clients are exempt from the Origin check
    assert page.request.post(f"{studio.base}/api/chats", headers=studio.headers, data={}).ok


def test_no_anthropic_or_claude_variable_reaches_a_child_of_the_server_and_config_merges(tmp_path, api):
    # the studio build stands in for every child (builds, the claude CLI): it fails when it sees one
    check = "process.exit(Object.keys(process.env).some((k) => /^(ANTHROPIC_|CLAUDE)/i.test(k)) ? 1 : 0)"
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"studioBuild": ["node", "-e", check]}), encoding="utf-8")
    with run_studio("--config", config, env={"ANTHROPIC_STUDIO_TEST": "1", "CLAUDE_STUDIO_TEST": "1"}) as s:
        assert built(s, api)["ok"] is True
        # the rest of the adapter config stays: the fonts still come from the kit
        assert api.get(f"{s.base}/ui/fonts.css", headers=s.headers).status == 200


def run_job(page, name):
    """Start a job from the studio page; returns {status, events} with that job's events until its end."""
    return page.evaluate("""async (name) => {
        const events = [];
        let ended;
        const end = new Promise((resolve) => { ended = resolve; });
        const off = studio.on('job', (e) => { if (e.name === name) { events.push(e); if (e.state !== 'running') ended(); } });
        const { status } = await studio.api(`/api/jobs/${name}`, { confirm: true });
        if (status === 202) await end;
        off();
        return { status, events };
    }""", name)


def test_an_e2e_studio_runs_harmless_stand_ins_for_every_job_so_tests_never_publish(kit_copy, tmp_path, page):
    # a stub for the copy's Netlify script and no Netlify login in APPDATA: not even the real job could publish
    tools = kit_copy / "deck" / "tools"
    (tools / "publish_netlify.ps1").write_text("Set-Content -LiteralPath (Join-Path $PSScriptRoot 'stub-ran.txt') -Value ran\n",
                                              encoding="utf-8")
    with run_studio(kit=kit_copy, env={"APPDATA": str(tmp_path)}) as s:  # no --config of its own
        open_studio(page, s)
        for name in ["publish", "export-pdf", "beamer"]:
            run = run_job(page, name)
            assert run["status"] == 202
            assert run["events"][-1]["state"] == "ok", name
            assert [e["line"] for e in run["events"] if "line" in e and not e["line"].startswith("> ")] == [
                f"stand-in for the {name} job"]
            assert not (tools / "stub-ran.txt").exists()


def test_a_second_studio_on_the_same_data_dir_does_not_start_and_hands_over_the_running_ones_url(studio, api):
    second = subprocess.Popen(
        [sys.executable, "-m", "deck_studio", "--kit", str(studio.kit), "--port", "0", "--data", str(studio.data),
         "--fake-agent", str(SCENARIOS), "--no-open"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", **plataforma.NEW_GROUP)
    try:
        out, err = second.communicate(timeout=20)
    except subprocess.TimeoutExpired:
        out, err = "", "it kept running"
    finally:
        plataforma.kill_tree(second.pid)
        second.wait()
    assert "O Deck Studio já está aberto com esta pasta de dados" in err
    assert out.splitlines() == [f"DECK_STUDIO_URL={studio.url}"]
    assert second.returncode == 0
    assert api.get(f"{studio.base}/api/status", headers=studio.headers).status == 200


def test_a_script_a_slide_holds_never_runs_in_the_studio_deck_while_the_decks_own_scripts_do(kit_copy, page):
    # the agent writes slides with no approval card: their code must not reach the studio page (approvals, Publicar)
    slide = kit_copy / "deck" / "src" / "slides" / "03-data.html"
    planted = ("<script>parent.planted = 'script'</script>"
               "<img src=\"nothing.png\" onerror=\"parent.planted = 'handler'\" alt=\"\">")
    slide.write_text(slide.read_text(encoding="utf-8").replace("</section>", planted + "</section>", 1), encoding="utf-8")
    with run_studio(kit=kit_copy) as s:
        open_studio(page, s)  # the deck's load event: its scripts ran and its images loaded or failed
        go_slide(page, 13, 2)
        assert slide_and_step(page) == (13, 2)  # the engine runs
        assert page.evaluate("() => window.planted") is None
