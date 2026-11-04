"""Seam 2: the real Agent SDK on the author's subscription, run by hand: STUDIO_LIVE=1 pytest tests/live -s.

A real studio server (no fake agent, environment scrubbed) on a kit copy, driven through its HTTP API, with its
event stream recorded. Small prompts; the default chat model (Opus)."""
import contextlib
import http.client
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pymupdf
import pytest

from tests.helpers.kit_copy import make_kit_copy, remove_kit_copy

pytestmark = pytest.mark.skipif(os.environ.get("STUDIO_LIVE") != "1", reason="live SDK smoke: set STUDIO_LIVE=1")

ROOT = Path(__file__).resolve().parents[2]
SELECTED_SKILLS = {"frontend-design:frontend-design", "impeccable:impeccable", "dataviz",
                   "deck-studio-skills:humanizer", "deck-studio-skills:thesis-review"}  # docs/PYTHON.md defaults
TURN_TIMEOUT = 300


class Live:
    """The server, its token, every event it published since start and the lines of its stderr."""

    def __init__(self, base, token, kit, data, stderr):
        self.base, self.token, self.kit, self.data, self.stderr = base, token, kit, data, stderr
        self.events, self._cond = [], threading.Condition()
        u = urlsplit(base)
        self._conn = http.client.HTTPConnection(u.hostname, u.port)  # no timeout: the stream may idle for long
        self._conn.request("GET", "/api/events", headers={"x-studio-token": token})
        response = self._conn.getresponse()
        threading.Thread(target=self._read, args=(response,), daemon=True).start()

    def _read(self, response):
        with contextlib.suppress(OSError):  # the server is killed at the end
            for line in response:
                if line.startswith(b"data: "):
                    with self._cond:
                        self.events.append({**json.loads(line[6:]), "t": time.monotonic()})
                        self._cond.notify_all()

    def wait(self, test, timeout=TURN_TIMEOUT):
        with self._cond:
            return self._cond.wait_for(lambda: next((e for e in self.events if test(e)), None), timeout)

    def call(self, path, body=None):
        request = urllib.request.Request(f"{self.base}{path}", data=None if body is None else json.dumps(body).encode(),
                                         headers={"x-studio-token": self.token, "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=60) as r:
            return json.loads(r.read())

    def turn(self, chat_id, text):
        """Send one message and wait for its turn-end, denying every approval it asks for (none is expected):
        the turn's events, after printing a summary of it."""
        t0 = time.monotonic()
        turn_id = self.call(f"/api/chats/{chat_id}/messages", {"text": text})["turnId"]
        denied = set()
        while not self.wait(lambda e: e.get("kind") == "turn-end" and e.get("turnId") == turn_id, timeout=1):
            for e in [e for e in self.events if e["type"] == "approval" and e.get("turnId") == turn_id]:
                if e["state"] == "pending" and e["id"] not in denied:
                    denied.add(e["id"])
                    self.call(f"/api/approvals/{e['id']}", {"decision": "deny"})
            events = [e for e in self.events if e.get("turnId") == turn_id]
            assert time.monotonic() - t0 < TURN_TIMEOUT, f"the turn did not end: {events}"
        events = [e for e in self.events if e.get("turnId") == turn_id]
        print(f"\n  {round(time.monotonic() - t0, 1)} s; tools: "
              f"{[(e['name'], e['summary']) for e in kinds(events, 'tool') if e['state'] == 'running']}; approvals "
              f"denied: {[(e['tool'], e['summary']) for e in events if e['type'] == 'approval' and e.get('tool')]}; "
              f"answer: {' '.join(e['text'] for e in kinds(events, 'text'))[:300]!r}")
        return events


@pytest.fixture(scope="module")
def live():
    kit = make_kit_copy()
    data = Path(tempfile.mkdtemp(prefix="deck-studio-live-"))
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("ANTHROPIC_", "CLAUDE"))}
    proc = subprocess.Popen([sys.executable, "-m", "deck_studio", "--kit", str(kit), "--port", "0", "--data", str(data),
                             "--no-open"], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            encoding="utf-8", env=env)
    stderr = []  # kept, and shown as it comes

    def drain_stderr():
        for line in proc.stderr:
            stderr.append(line)
            sys.stderr.write(line)
    threading.Thread(target=drain_stderr, daemon=True).start()
    try:
        url = next(m[1] for line in proc.stdout if (m := re.match(r"^DECK_STUDIO_URL=(\S+)$", line.strip())))
        threading.Thread(target=lambda: [None for _ in proc.stdout], daemon=True).start()  # keep stdout drained
        u = urlsplit(url)
        yield Live(f"{u.scheme}://{u.netloc}", parse_qs(u.query)["t"][0], kit, data, stderr)
    finally:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        proc.wait()
        remove_kit_copy(kit)
        shutil.rmtree(data, ignore_errors=True)


@pytest.fixture(scope="module")
def chat(live):
    return live.call("/api/chats", {})["id"]


def kinds(events, kind):
    return [e for e in events if e.get("kind") == kind]


def test_a_read_only_question_is_answered_on_the_subscription_with_only_the_selected_skills(live, chat):
    events = live.turn(chat, "Quantas tags <section> tem o arquivo deck/src/slides/03-data.html? "
                             "Responda só com o número.")
    assert live.call("/api/status")["auth"] == "ok"
    assert not kinds(events, "error")
    init = kinds(events, "init")[0]
    assert "opus" in init["model"]
    assert set(init["skills"]) == SELECTED_SKILLS
    assert "".join(e["text"] for e in kinds(events, "text")).strip()
    assert all(e.get("name") != "ToolSearch" for e in kinds(events, "tool"))  # the deck tools load directly
    assert kinds(events, "turn-end")[0]["files"] == []


def test_a_chat_is_an_sdk_session_which_the_cli_leaves_out_of_its_resume_list(live, chat):
    """SPEC story 23: the CLI's /resume list leaves out the sessions whose transcript says entrypoint sdk-ts, sdk-py
    or sdk-cli (read in the bundled CLI 2.1.310)."""
    live.turn(chat, "Responda só com a palavra ok.")
    session = json.loads((live.data / "chats" / f"{chat}.json").read_text(encoding="utf-8"))["sessionId"]
    [transcript] = (Path.home() / ".claude" / "projects").glob(f"*/{session}.jsonl")
    lines = [json.loads(line) for line in transcript.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert {e["entrypoint"] for e in lines if "entrypoint" in e} == {"sdk-py"}


def test_the_guard_denies_a_write_to_data(live, chat):
    events = live.turn(chat, "Teste do bloqueio do estúdio: chame a ferramenta Write uma vez para criar "
                             "data/smoke.txt com o texto x. O estúdio deve recusar, e é isso que estou testando: tente "
                             "mesmo assim, sem usar outras ferramentas, e depois diga numa linha o que aconteceu.")
    writes = [e for e in kinds(events, "tool") if e.get("name") == "Write"]
    assert writes, "the agent did not try the Write"
    ends = {e["id"]: e for e in kinds(events, "tool") if e["state"] != "running"}
    assert ends[writes[0]["id"]]["state"] == "denied"
    assert "data/** é protegido" in ends[writes[0]["id"]]["detail"]
    assert not (live.kit / "data" / "smoke.txt").exists()
    assert kinds(events, "turn-end")[0]["files"] == []


def test_an_allowed_edit_to_a_slide_rebuilds_the_deck(live, chat):
    events = live.turn(chat, "No arquivo deck/src/slides/03-data.html, troque o texto "
                             "'Labels per protein (mean)' por 'Mean labels per protein' com a ferramenta Edit. "
                             "Depois confira o slide 13 com screenshot_slide. Não mude mais nada.")
    tools = kinds(events, "tool")
    edit = next(e for e in tools if e.get("name") == "Edit")
    assert any(e["id"] == edit["id"] and e["state"] == "ok" for e in tools)
    # the edit's PostToolUse hook rebuilt the deck and put the change on screen during the turn
    start, end = kinds(events, "user")[0]["t"], kinds(events, "turn-end")[0]["t"]
    during = [e for e in live.events if start < e["t"] < end]
    shown = [e for e in during if e["type"] in ("build", "deck-swap", "deck-reload") or e.get("kind") == "tool"]
    print("  timeline:", [(round(e["t"] - start, 2), e["type"], e.get("kind"), e.get("name") or e.get("state"),
                           e.get("running")) for e in shown])
    assert any(e["type"] == "build" and e["ok"] and not e["running"] and e["t"] > edit["t"] for e in during)
    assert any(e["type"] == "deck-reload" or e["type"] == "deck-swap" and
               any(p["part"] == "03-data.html" for p in e["parts"]) for e in during)
    assert "Mean labels per protein" in (live.kit / "deck/src/slides/03-data.html").read_text(encoding="utf-8")
    assert kinds(events, "turn-end")[0]["files"] == ["deck/src/slides/03-data.html"]


def test_a_tool_result_over_one_mib_reaches_the_agent_and_the_turn_ends_normally(live, chat):
    """On 2026-10-28 a Read of a PNG made a 1,268,668-byte stream-json line, over the SDK's default buffer of 1 MiB,
    and the turn died. The line holds the image twice (the tool result and its copy for the SDK). The CLI passes a
    PNG through as it is only up to its own size target (it made a 1 MB noisy PNG a 313 KB JPEG, in an 835 KB line),
    so this noisy RGB PNG has about 450 KB: under that target, and over 1 MiB in the line."""
    width = height = 388
    image = live.kit / "context" / "ruido.png"
    image.parent.mkdir(exist_ok=True)
    pymupdf.Pixmap(pymupdf.csRGB, width, height, random.Random(7).randbytes(width * height * 3), False).save(image)
    assert 2 * image.stat().st_size * 4 / 3 > 1 << 20
    events = live.turn(chat, "Leia a imagem context/ruido.png com a ferramenta Read e responda numa só palavra o que "
                             "ela mostra.")
    assert not kinds(events, "error")
    [read] = [e for e in kinds(events, "tool") if e.get("name") == "Read"]
    assert [e["state"] for e in kinds(events, "tool") if e["id"] == read["id"]] == ["running", "ok"]
    assert "".join(e["text"] for e in kinds(events, "text")).strip()
    assert kinds(events, "turn-end")[0]["files"] == []
    assert not [line for line in live.stderr if "Traceback" in line or "Exception ignored" in line]


PT_WORDS = {"que", "o", "a", "de", "do", "da", "em", "um", "uma", "é", "não", "os", "as", "com", "para", "slide"}
EN_WORDS = {"the", "is", "and", "of", "to", "in", "this", "that", "it", "with", "for", "slide"}


def test_every_message_is_in_portuguese_even_asked_in_english_about_english_slides(live, chat):
    """Finding of the recorded end-to-end test (2026-11-04): a note between tool calls came out in English."""
    events = live.turn(chat, "Read deck/src/slides/03-data.html and tell me in two short sentences what its first "
                             "slide is about.")
    text = " ".join(e["text"] for e in kinds(events, "text")).lower()
    words = re.findall(r"[a-zà-ú]+", text)
    pt = sum(w in PT_WORDS - EN_WORDS for w in words)
    en = sum(w in EN_WORDS - PT_WORDS for w in words)
    print(f"\n  pt words {pt}, en words {en}: {text[:300]!r}")
    assert pt > 3 * max(en, 1), text
