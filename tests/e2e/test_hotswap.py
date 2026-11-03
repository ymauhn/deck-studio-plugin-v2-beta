"""[hotswap]: an edit to slide files swaps their slides in place (deck-swap); any other change reloads the deck.

The server runs in this process. A direct edit goes through POST /api/edit-text. An agent's write is made the way
its PostToolUse hook makes it ([loop-agent]): the test writes the file, then calls builder.sources_changed."""
import asyncio
import shutil
import socket
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import expect

from deck_studio.config import load_config, merge
from deck_studio.server.app import create_app
from deck_studio.server.state import StudioState
from tests.e2e.conftest import (SAFE_JOBS, SCENARIOS, Studio, center, deck_of, go_slide, open_studio, slide_and_step,
                                wait_until)
from tests.helpers.kit_copy import make_kit_copy, remove_kit_copy

SLIDES = "deck/src/slides"


@dataclass
class Server:
    studio: Studio
    state: StudioState
    loop: asyncio.AbstractEventLoop

    def change(self, *paths):
        """builder.sources_changed(paths) on the server's loop; returns a future of the build state."""
        return asyncio.run_coroutine_threadsafe(self.state.builder.sources_changed(list(paths)), self.loop)


@pytest.fixture(scope="module")
def server():
    """The studio server on a thread of this process: a kit copy, a temp data dir and the fake agent."""
    kit, data = make_kit_copy(), Path(tempfile.mkdtemp(prefix="deck-studio-data-"))
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    state = StudioState(merge(load_config(kit), SAFE_JOBS), data, port, fake_agent=SCENARIOS)
    uv = uvicorn.Server(uvicorn.Config(create_app(state), log_level="warning", access_log=False,
                                       timeout_graceful_shutdown=1))
    loops = []

    async def serve():  # as __main__ does; asyncio.run then cancels what features left running
        loops.append(asyncio.get_running_loop())
        await uv.serve(sockets=[sock])

    thread = threading.Thread(target=asyncio.run, args=(serve(),))
    thread.start()
    try:
        wait_until(lambda: uv.started or not thread.is_alive(), 30, "the studio server")
        assert uv.started, "the studio server did not start"
        base = f"http://127.0.0.1:{port}"
        yield Server(Studio(f"{base}/?t={state.token}", base, state.token, kit, data, None), state, loops[0])
    finally:
        if thread.is_alive():
            asyncio.run_coroutine_threadsafe(state.builder.wait(), loops[0]).result(60)  # no build left in the copy
            uv.should_exit = True
            thread.join(30)
        remove_kit_copy(kit)
        shutil.rmtree(data, ignore_errors=True)


def read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def deck_frame(page):
    return page.locator('iframe[title="Deck"]').element_handle().content_frame()


def mark_window(page):
    deck_of(page).locator("html").evaluate("() => { window.marker = 'no reload'; }")


def marker(page):
    return deck_of(page).locator("html").evaluate("() => window.marker ?? null")


def hold(page, url):
    """Hold the page's next request for url; the returned release() waits for that request and lets it go."""
    held = []
    page.route(url, lambda route: held.append(route), times=1)

    def release():
        for _ in range(1500):  # 15 s; Playwright hands a request over only while the test calls it
            if held:
                return held[0].continue_()
            page.wait_for_timeout(10)
        raise AssertionError(f"no request for {url}")
    return release


def test_a_direct_text_edit_swaps_the_slide_in_place_on_the_same_slide_and_step_without_a_reload(server, page):
    open_studio(page, server.studio)
    go_slide(page, 13, 3)
    mark_window(page)
    old = "Labels per protein (mean): 25.91 BP, 12.48 CC, 7.55 MF"  # 03-data.html:9:5, fragment 3 of s13
    new = "Mean labels per protein: 25.91 BP, 12.48 CC, 7.55 MF"
    edit = {"loc": {"file": f"{SLIDES}/03-data.html", "line": 9, "col": 5}, "childIndex": 0, "oldText": old, "newText": new}

    t0 = time.perf_counter()
    page.evaluate("(edit) => { window.saved = studio.api('/api/edit-text', edit); }", edit)
    deck_frame(page).wait_for_function(
        "text => document.querySelector('section.slide.active')?.textContent.includes(text)", arg=new)
    print(f"\nedit to screen, swapped: {(time.perf_counter() - t0) * 1000:.0f} ms")
    assert page.evaluate("() => window.saved")["status"] == 200

    assert marker(page) == "no reload"
    assert slide_and_step(page) == (13, 3)
    expect(deck_of(page).locator("#s13 li", has_text=new)).to_be_visible()  # its fragment, step 3, is shown
    expect(deck_of(page).locator("#s13", has_text=old)).to_have_count(0)


def test_a_deck_that_loads_before_the_studio_page_script_still_swaps(server, page):
    def late(route):
        page.wait_for_timeout(3000)  # meanwhile the deck loads and runs its scripts
        route.continue_()

    page.route("**/ui/app.js", late)
    open_studio(page, server.studio)
    go_slide(page, 14, 0)
    mark_window(page)
    part = server.studio.kit / SLIDES / "03-data.html"
    old, new = "STRING v11.5: one aggregated network", "STRING v11.5: a single aggregated network"
    write(part, read(part).replace(old, new))

    assert server.change(str(part)).result(60)["ok"] is True
    expect(deck_of(page).locator("#s14 h2")).to_have_text(new)
    assert marker(page) == "no reload"


def test_an_agent_change_to_the_css_of_a_slide_file_is_swapped_in_too(server, page):
    open_studio(page, server.studio)
    go_slide(page, 13, 0)
    mark_window(page)
    part = server.studio.kit / SLIDES / "03-data.html"
    src = read(part)
    assert src.count("</style>") == 1

    write(part, src.replace("</style>", "#s13 h2.title { color: rgb(1, 2, 3); }</style>"))
    assert server.change(str(part)).result(60)["ok"] is True  # an absolute path, as the agent's tools give
    expect(deck_of(page).locator("#s13 h2")).to_have_css("color", "rgb(1, 2, 3)")
    assert marker(page) == "no reload"


def test_the_picker_selects_a_swapped_element_at_its_new_source_location(server, page):
    open_studio(page, server.studio)
    go_slide(page, 43, 1)
    mark_window(page)
    select = page.get_by_role("button", name="Selecionar (S)")
    chips = page.get_by_role("list", name="Seleção").get_by_role("listitem")
    marks = deck_of(page).locator(".studio-selected")
    select.click()
    page.mouse.click(*center(deck_of(page).locator("#s43 li", has_text="Single seed;")))
    expect(chips).to_have_count(1)
    expect(chips.first).to_contain_text("06-conclusions.html:24")

    part = server.studio.kit / SLIDES / "06-conclusions.html"
    src = read(part)
    # a new line above the slide moves its elements one line down; the agent's tools give absolute paths
    write(part, src.replace('<section class="slide" id="s43"', '<!-- new line -->\r\n<section class="slide" id="s43"')
          .replace("Single seed;", "One seed;"))
    assert server.change(str(part)).result(60)["ok"] is True
    bullet = deck_of(page).locator("#s43 li", has_text="One seed;")
    expect(bullet).to_be_visible()
    assert marker(page) == "no reload"
    expect(marks).to_have_count(0)  # the box it marked went with the old slide, as after a reload

    expect(select).to_have_attribute("aria-pressed", "true")  # still in select mode
    page.mouse.click(*center(bullet))
    expect(chips).to_have_count(1)
    expect(chips.first).to_contain_text("06-conclusions.html:25")
    [selected] = page.evaluate("() => studio.selection.get()")
    assert (selected["slideId"], selected["slide"], selected["step"]) == ("s43", 43, 1)
    assert selected["loc"] == {"file": "deck/src/slides/06-conclusions.html", "line": 25, "col": 5}
    assert selected["text"].startswith("One seed; the 0.5 pp floor")
    expect(marks.filter(visible=True)).to_have_count(1)


def open_on_slide_13_step_2(server, page):
    open_studio(page, server.studio)
    go_slide(page, 13, 2)
    mark_window(page)


def deck_on(page, slide, step):
    """Wait until the deck is on that slide and step; until its engine starts, window.deck is the #deck element."""
    deck_frame(page).wait_for_function("([n, f]) => typeof window.deck?.state === 'function' "
                                       "&& window.deck.state().slide === n && window.deck.state().fragment === f",
                                       arg=[slide, step], timeout=15_000)


def expect_reloaded_on_slide_13_step_2(page):
    expect(deck_of(page).locator("#s13 h2")).to_be_visible()  # the reloaded deck goes back to its slide
    assert marker(page) is None
    deck_on(page, 13, 2)  # the slide comes back from the URL hash as the deck starts, the step at its load event


def test_an_edit_to_any_other_file_rebuilds_and_reloads_the_deck_on_the_same_slide_and_step(server, page):
    open_on_slide_13_step_2(server, page)
    css = server.studio.kit / "deck/src/deck.css"

    t0 = time.perf_counter()
    write(css, read(css) + "\n#s13 h2.title { background-color: rgb(4, 5, 6); }\n")
    done = server.change("deck/src/deck.css")
    deck_frame(page).wait_for_function("""() => typeof window.deck?.state === 'function' && window.deck.state().slide === 13
        && getComputedStyle(document.querySelector('#s13 h2')).backgroundColor === 'rgb(4, 5, 6)'""")
    print(f"\nedit to screen, reloaded: {(time.perf_counter() - t0) * 1000:.0f} ms")
    assert done.result(60)["ok"] is True
    expect_reloaded_on_slide_13_step_2(page)


def test_a_slide_edit_made_while_the_deck_reloads_reaches_the_reloaded_deck(server, page):
    # back-to-back agent edits: deck.css, then a slide file; the reload asks for /deck during the part build
    open_studio(page, server.studio)
    go_slide(page, 22, 0)
    release_deck, release_swap = hold(page, "**/deck"), hold(page, "**/ui/deck/swap.js")
    css, part = server.studio.kit / "deck/src/deck.css", server.studio.kit / SLIDES / "04-method.html"
    old, new = "ProtT5-XL-U50, three layers, frozen", "ProtT5-XL-U50: three frozen layers"

    write(css, read(css) + "\n#s22 h2.title { letter-spacing: 1px; }\n")
    assert server.change("deck/src/deck.css").result(60)["ok"] is True  # deck-reload: the deck asks for /deck
    write(part, read(part).replace(old, new))
    done = server.change(str(part))  # its part build starts
    release_deck()  # /deck reaches the server during the part build
    assert done.result(60)["ok"] is True  # the swap went out, then the full build
    release_swap()  # only now does the reloaded deck listen for swaps: it missed this one
    expect(deck_of(page).locator("#s22 h2")).to_have_text(new)


def test_a_slide_file_whose_slides_changed_reloads_the_deck_on_the_same_slide_and_step(server, page):
    open_on_slide_13_step_2(server, page)
    backup = server.studio.kit / SLIDES / "07-backup.html"
    write(backup, read(backup) + '\r\n<section class="slide backup" id="b9" data-part="Backup">\r\n'
          '<h2 class="title">One more backup slide</h2>\r\n</section>\r\n')  # a new slide: no swap

    assert server.change(f"{SLIDES}/07-backup.html").result(60)["ok"] is True
    expect(deck_of(page).locator("#b9")).to_have_count(1)
    expect_reloaded_on_slide_13_step_2(page)


def test_a_deleted_slide_file_rebuilds_and_reloads_the_deck_on_the_same_slide_and_step(server, page):
    open_on_slide_13_step_2(server, page)
    (server.studio.kit / SLIDES / "07-backup.html").unlink()  # its part build fails

    assert server.change(f"{SLIDES}/07-backup.html").result(60)["ok"] is True
    expect(deck_of(page).locator("#b1")).to_have_count(0)
    expect_reloaded_on_slide_13_step_2(page)
