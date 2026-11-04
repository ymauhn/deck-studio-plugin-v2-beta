"""Seam 1 fixtures: a studio server (kit copy, fake agent) per test module, and pages that only reach it.

Reuse in a feature test:
- `studio`: the module's server; override `studio_args` in the module to add CLI args (say, --config).
- `run_studio(*args)`: a context manager for one more server of your own. Every job of the kit's own config runs a
  harmless stand-in (safe_jobs) unless the module's --config gives it a command of its own.
- `studio_page`: a page opened through the launch URL, with the deck and the UI ready.
- `api`: an HTTP client with no cookies; send `studio.headers` to authenticate.
- helpers to import: deck_of, deck_state, slide_and_step, go_slide, center, open_studio, wait_until, built.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import expect

from deck_studio.config import load_config, merge
from tests.helpers.kit_copy import make_kit_copy, remove_kit_copy, remove_tree

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = ROOT / "tests" / "fixtures" / "scenarios"


def safe_jobs(kit):
    """Every job of the kit's adapter (NEXUS-GO's, or a project's generic one) as a harmless stand-in: an e2e studio
    never exports with the kit's tools or publishes."""
    config = load_config(kit)
    stand_in = lambda jobs, tag="": {name: [[sys.executable, "-c", f"print('stand-in for the {name} job{tag}')"]]  # noqa: E731
                                     for name in jobs}
    # a language tree (NEXUS-GO's deck/src-pt) brings jobs of its own: stand-ins too
    return {"jobs": stand_in(config["jobs"]),
            "languageTrees": {lang: {"jobs": stand_in(tree.get("jobs", {}), f" ({lang})")}
                              for lang, tree in config.get("languageTrees", {}).items()}}


SAFE_JOBS = safe_jobs(ROOT)  # NEXUS-GO's jobs

expect.set_options(timeout=15_000)


@dataclass
class Studio:
    url: str  # launch URL: http://127.0.0.1:<port>/?t=<token>
    base: str  # http://127.0.0.1:<port>
    token: str
    kit: Path
    data: Path
    proc: subprocess.Popen

    @property
    def headers(self):
        return {"x-studio-token": self.token}


def _read_url(proc, timeout):
    """The DECK_STUDIO_URL the server prints when ready; stdout keeps draining afterwards."""
    found, done = [], threading.Event()

    def drain():
        for line in proc.stdout:
            m = re.match(r"^DECK_STUDIO_URL=(\S+)$", line.strip())
            if m and not found:
                found.append(m[1])
                done.set()
        done.set()

    threading.Thread(target=drain, daemon=True).start()
    done.wait(timeout)
    if not found:
        raise RuntimeError(f"the studio did not print its URL (exit code {proc.poll()})")
    return found[0]


@contextmanager
def run_studio(*args, kit=None, env=None, timeout=60):
    """Start `python -m deck_studio` on a fresh kit copy (or on `kit`) with a temp data dir and the fake agent.

    Extra CLI args go last; a --config among them is merged over safe_jobs(kit). `env` adds variables to the
    server's environment. The process tree is killed and the copy and data dir are removed at exit."""
    own_kit = kit is None
    kit = Path(kit) if kit else make_kit_copy()
    data = Path(tempfile.mkdtemp(prefix="deck-studio-data-"))
    args, config = [str(a) for a in args], safe_jobs(kit)
    if "--config" in args:
        i = args.index("--config")
        config = merge(config, json.loads(Path(args.pop(i + 1)).read_text(encoding="utf-8")))
        args.pop(i)
    (data / "e2e-config.json").write_text(json.dumps(config), encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "deck_studio", "--kit", str(kit), "--port", "0", "--data", str(data),
         "--fake-agent", str(SCENARIOS), "--no-open", "--config", str(data / "e2e-config.json"), *args],
        cwd=ROOT, stdout=subprocess.PIPE, text=True, encoding="utf-8", env={**os.environ, **(env or {})})
    try:
        url = _read_url(proc, timeout)
        u = urlsplit(url)
        yield Studio(url, f"{u.scheme}://{u.netloc}", parse_qs(u.query)["t"][0], kit, data, proc)
    finally:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        proc.wait()
        if own_kit:
            remove_kit_copy(kit)
        remove_tree(data)


@pytest.fixture(scope="module")
def studio_args():
    """Extra CLI args for this module's studio; override in a test module."""
    return []


@pytest.fixture(scope="module")
def studio(studio_args):
    with run_studio(*studio_args) as s:
        yield s


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    # reduced motion: the deck drops its transitions, so no half-faded slides
    return {**browser_context_args, "viewport": {"width": 1600, "height": 900},
            "reduced_motion": "reduce", "color_scheme": "light"}


@pytest.fixture
def page(page):
    """Pages reach only the studio itself: the deck links Google Fonts, the tests stay off the network."""
    page.route(lambda url: urlsplit(url).hostname not in ("127.0.0.1", "localhost"), lambda route: route.abort())
    return page


@pytest.fixture
def api(playwright):
    """An HTTP client without cookies."""
    context = playwright.request.new_context()
    yield context
    context.dispose()


@pytest.fixture
def studio_page(page, studio):
    open_studio(page, studio)
    return page


def wait_until(fn, timeout=15, message="condition"):
    """Poll fn until it returns something truthy; returns that value."""
    end = time.monotonic() + timeout
    while not (value := fn()):
        if time.monotonic() > end:
            raise AssertionError(f"timed out waiting for {message}")
        time.sleep(0.1)
    return value


def status_of(studio, api):
    return api.get(f"{studio.base}/api/status", headers=studio.headers).json()


def built(studio, api, timeout=60):
    """Wait until a build has finished and none runs; returns the build state of /api/status."""
    def done():
        b = status_of(studio, api)["build"]
        return b if b["ok"] is not None and not b["running"] else None
    return wait_until(done, timeout, "the studio build")


def deck_of(page):
    return page.frame_locator('iframe[title="Deck"]')


def deck_state(page):
    return deck_of(page).locator("html").evaluate("() => window.deck.state()")


def slide_and_step(page):
    state = deck_state(page)
    return state["slide"], state["fragment"]


def go_slide(page, n, step=0):
    deck_of(page).locator("html").evaluate("(_, [n, step]) => window.deck.go(n, step)", [n, step])


def center(locator):
    b = locator.bounding_box()
    return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2


def open_studio(page, studio):
    """Open the studio through its launch URL; wait for the deck (with the picker) and the UI to be ready."""
    page.goto(studio.url)
    deck_of(page).locator("html").evaluate(
        "() => new Promise((r) => (document.readyState === 'complete' ? r() : addEventListener('load', r)))")
    expect(page.locator("body[data-ready]")).to_be_attached()
