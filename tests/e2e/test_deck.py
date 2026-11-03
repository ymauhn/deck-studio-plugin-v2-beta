"""Slice 2: the studio deck (the kit's --studio build, served at /deck with the picker injected)."""
import re

from playwright.sync_api import expect

from tests.e2e.conftest import ROOT, built, deck_of, go_slide, slide_and_step, wait_until

STUDIO_OUT = "deck/build/studio/nexus-go-defense.html"


def test_the_server_runs_the_studio_build_at_startup_and_reports_the_build_state_in_api_status(studio, api):
    build = built(studio, api)
    assert build["ok"] is True
    assert build["ms"] > 0
    assert build["error"] is None
    # the kit copy is made without deck/build/studio, so this file comes from the server's build
    assert (studio.kit / STUDIO_OUT).exists()


def test_deck_serves_the_studio_deck_with_the_picker_script_injected(studio, api):
    def get(path):
        return api.get(f"{studio.base}{path}", headers=studio.headers)

    res = get("/deck")
    assert res.status == 200
    assert res.headers["content-type"].startswith("text/html")
    html = res.text()
    assert ('<li class="f" data-f="3" data-loc="deck/src/slides/03-data.html:9:5">'
            "Labels per protein (mean): 25.91 BP, 12.48 CC, 7.55 MF</li>") in html
    # picker.js, then the deck-side feature scripts, before the last </body>; the CSP's nonce lets them run
    nonce = re.search(r"'nonce-([\w-]+)'", res.headers["content-security-policy"])[1]
    assert re.search(rf'<script type="module" nonce="{nonce}" src="/ui/picker\.js"></script>\s*'
                     rf'(<script type="module" nonce="{nonce}" src="/ui/deck/[\w.-]+\.js"></script>\s*)*</body>\s*</html>\s*$',
                     html)
    picker = get("/ui/picker.js")
    assert picker.status == 200
    assert picker.headers["content-type"].startswith("text/javascript")


def test_the_iframe_shows_the_deck_its_keys_work_inside_it_and_deck_go_13_shows_the_data_slide(studio, page):
    page.goto(studio.url)
    deck = deck_of(page)
    expect(deck.locator("#s01")).to_be_visible()

    go_slide(page, 13)
    expect(deck.locator("#s13 h2")).to_have_text("Data: a CAFA5-derived corpus")
    expect(deck.locator("#s13 h2")).to_be_visible()
    expect(deck.locator("#s01")).to_be_hidden()

    body = deck.locator("body")
    body.press("ArrowRight")
    assert slide_and_step(page) == (13, 1)
    for key in ["2", "1", "g"]:
        body.press(key)
    assert slide_and_step(page) == (21, 0)
    body.press("t")
    expect(deck.locator("html")).to_have_attribute("data-theme", "dark")


def test_the_ui_loads_its_fonts_from_the_kit_deck_build_fonts_css_served_by_the_server(studio, page, api):
    res = api.get(f"{studio.base}/ui/fonts.css", headers=studio.headers)
    assert res.status == 200
    assert res.headers["content-type"].startswith("text/css")
    assert res.body() == (studio.kit / "deck" / "build" / "fonts.css").read_bytes()

    page.goto(studio.url)
    loaded = "() => [...document.fonts].filter((f) => f.status === 'loaded').map((f) => f.family.replace(/\"/g, ''))"
    wait_until(lambda: {"Atkinson Hyperlegible Next", "Bricolage Grotesque"} <= set(page.evaluate(loaded)),
               message="the deck fonts")


def test_api_ui_features_lists_the_feature_files_present_and_deck_injects_the_deck_side_ones(studio, api):
    ui = ROOT / "deck_studio" / "ui"
    listed = api.get(f"{studio.base}/api/ui-features", headers=studio.headers).json()
    assert listed == {"app": [f"/ui/features/{f.name}" for f in sorted((ui / "features").glob("*.js"))],
                      "deck": [f"/ui/deck/{f.name}" for f in sorted((ui / "deck").glob("*.js"))],
                      "css": [f"/ui/features/{f.name}" for f in sorted((ui / "features").glob("*.css"))]}
    html = api.get(f"{studio.base}/deck", headers=studio.headers).text()
    for url in listed["deck"]:
        assert re.search(rf'<script type="module" nonce="[\w-]+" src="{re.escape(url)}"></script>', html), url
    for url in listed["app"] + listed["deck"]:
        assert api.get(f"{studio.base}{url}", headers=studio.headers).headers["content-type"].startswith("text/javascript")


MEMBERS = """() => {
    const kinds = (o, names) => Object.fromEntries(names.map((n) => [n, typeof o?.[n]]));
    const s = window.studio;
    return {
        studio: kinds(s, ['api', 'on']),
        selection: kinds(s.selection, ['get', 'set', 'subscribe', 'clear']),
        deck: { ...kinds(s.deck, ['win', 'go', 'state', 'reload']), frame: s.deck.frame === document.querySelector('iframe') },
        ui: kinds(s.ui, ['addToolbarButton', 'addPanel', 'toast', 'confirm']),
        composer: kinds(s.composer, ['insert', 'setText', 'focus']),
        chat: kinds(s.chat, ['send', 'current', 'append']),
        mode: kinds(s.mode, ['get', 'set', 'subscribe']),
    };
}"""


def test_window_studio_has_every_documented_member(studio_page):
    members = studio_page.evaluate(MEMBERS)
    frame = members["deck"].pop("frame")
    assert frame is True
    assert {group: set(kinds.values()) for group, kinds in members.items()} == {
        group: {"function"} for group in ["studio", "selection", "deck", "ui", "composer", "chat", "mode"]}
    assert {group: sorted(kinds) for group, kinds in members.items()} == {
        "studio": ["api", "on"], "selection": ["clear", "get", "set", "subscribe"],
        "deck": ["go", "reload", "state", "win"], "ui": ["addPanel", "addToolbarButton", "confirm", "toast"],
        "composer": ["focus", "insert", "setText"], "chat": ["append", "current", "send"],
        "mode": ["get", "set", "subscribe"]}


def test_studio_ui_adds_a_toolbar_button_a_panel_a_toast_and_an_in_page_confirm(studio_page):
    page = studio_page
    page.evaluate("""() => studio.ui.addToolbarButton({ id: 'probe', label: 'Sonda', title: 'Botão de teste',
        pressed: false, onClick: () => { window.clicked = true; } })""")
    button = page.get_by_role("region", name="Deck").get_by_role("button", name="Sonda")
    expect(button).to_have_attribute("aria-pressed", "false")
    button.click()
    assert page.evaluate("() => window.clicked") is True

    page.evaluate("""() => studio.ui.addPanel({ id: 'probe-panel', title: 'Painel de teste', side: 'left',
        element: Object.assign(document.createElement('p'), { textContent: 'conteúdo' }) })""")
    expect(page.get_by_role("region", name="Painel de teste")).to_contain_text("conteúdo")

    page.evaluate("() => studio.ui.toast('Exportação pronta', 'ok')")
    expect(page.get_by_role("status").filter(has_text="Exportação pronta")).to_be_visible()

    page.evaluate("() => { window.answer = studio.ui.confirm('Publicar agora?'); }")
    dialog = page.get_by_role("dialog")
    expect(dialog).to_contain_text("Publicar agora?")
    dialog.get_by_role("button", name="Confirmar").click()
    assert page.evaluate("() => window.answer") is True
    expect(dialog).to_have_count(0)
    page.evaluate("() => { window.answer = studio.ui.confirm('Publicar agora?'); }")
    page.get_by_role("dialog").get_by_role("button", name="Cancelar").click()
    assert page.evaluate("() => window.answer") is False


def test_studio_selection_composer_chat_and_mode_drive_the_page(studio_page):
    page = studio_page
    item = {"slideId": "s13", "slide": 13, "step": 3, "part": "03-data.html",
            "loc": {"file": "deck/src/slides/03-data.html", "line": 9, "col": 5}, "tag": "li", "classes": ["f"],
            "text": "x", "outerHTML": "<li>x</li>", "kind": "text", "rect": {"x": 900, "y": 300, "w": 500, "h": 40}}
    page.evaluate("""(item) => { window.seen = []; studio.selection.subscribe((list) => window.seen.push(list.length));
        studio.selection.set([item]); }""", item)
    chips = page.get_by_role("list", name="Seleção").get_by_role("listitem")
    expect(chips).to_have_count(1)
    expect(chips.first).to_contain_text("03-data.html:9")
    assert page.evaluate("() => studio.selection.get()") == [item]
    page.evaluate("() => studio.selection.clear()")
    expect(chips).to_have_count(0)
    assert page.evaluate("() => window.seen") == [1, 0]

    box = page.get_by_role("textbox", name="Mensagem")
    page.evaluate("() => { studio.composer.setText('Encurte'); studio.composer.focus(); studio.composer.insert(' isto'); }")
    expect(box).to_have_value("Encurte isto")
    expect(box).to_be_focused()

    assert page.evaluate("() => studio.chat.current().model") == "opus"
    page.evaluate("""() => studio.chat.append(Object.assign(document.createElement('article'),
        { className: 'card', ariaLabel: 'Cartão de teste', textContent: 'um cartão' }))""")
    expect(page.get_by_role("log", name="Conversa").get_by_role("article", name="Cartão de teste")).to_have_text("um cartão")

    assert page.evaluate("() => studio.mode.get()") == "html"
    page.evaluate("() => { window.modes = []; studio.mode.subscribe((m) => window.modes.push(m)); studio.mode.set('beamer'); }")
    assert page.evaluate("() => [studio.mode.get(), window.modes]") == ["beamer", ["beamer"]]


def test_studio_deck_reload_reloads_the_deck_at_the_same_slide_and_step(studio_page):
    page = studio_page
    page.evaluate("() => studio.deck.go(13, 2)")
    assert page.evaluate("() => [studio.deck.state().slide, studio.deck.state().fragment]") == [13, 2]
    page.evaluate("() => { studio.deck.win().beforeReload = true; }")
    page.evaluate("() => studio.deck.reload()")
    assert page.evaluate("() => studio.deck.win().beforeReload") is None
    assert slide_and_step(page) == (13, 2)


def until(page, fn, message):
    """Poll fn while Playwright keeps handing the page's requests to the routes."""
    for _ in range(1500):
        if fn():
            return
        page.wait_for_timeout(10)
    raise AssertionError(f"timed out waiting for {message}")


def test_a_deck_still_starting_fails_no_feature_and_a_reload_asked_meanwhile_still_reloads_it(studio, page):
    """Until the deck's engine starts (its page is still parsing), the deck window's `deck` is its #deck element."""
    held, app = [], []

    def deck(route):  # the deck stops just before its engine, until the test lets it go on
        response = route.fetch()
        html = response.text()
        i = html.rfind("<script>")
        nonce = re.search(r"'nonce-([\w-]+)'", response.headers["content-security-policy"])[1]  # the deck's CSP
        route.fulfill(response=response, body=f'{html[:i]}<script nonce="{nonce}" src="/hold-engine.js"></script>{html[i:]}')

    errors = []
    page.on("console", lambda m: m.type == "error" and errors.append(m.text))
    page.route("**/deck", deck)
    page.route("**/hold-engine.js", lambda route: held.append(route))
    page.route("**/ui/app.js", lambda route: app.append(route), times=1)
    page.goto(studio.url, wait_until="commit")
    until(page, lambda: held and app, "the deck to stop before its engine")
    app[0].continue_()  # the studio page and its features load while the deck has not started
    expect(page.locator("body[data-ready]")).to_be_attached()

    page.evaluate("() => { window.reloaded = studio.deck.reload(); }")  # as a deck-reload event does
    until(page, lambda: len(held) == 2, "the reloaded deck to stop before its engine")
    held[1].fulfill(body="", content_type="text/javascript")
    page.evaluate("() => window.reloaded")
    expect(page.get_by_role("status", name="Passo atual")).to_have_text(re.compile(r"^passo 1 de \d+$"))
    assert [e for e in errors if "não carregou" in e or "TypeError" in e] == []


def test_a_slide_file_changed_outside_the_studio_is_built_again_when_the_deck_loads(studio, api):
    built(studio, api)
    part = studio.kit / "deck/src/slides/05-results.html"
    old, new = "One or two hops, high retention", "One or two hops keep retention high"
    # as an editor or a shell command would: the studio hears nothing about it
    part.write_bytes(part.read_bytes().replace(old.encode(), new.encode()))
    html = api.get(f"{studio.base}/deck", headers=studio.headers).text()  # a reload of the deck, as the toasts advise
    assert f'">{new}</h2>' in html
    assert old not in html


def test_a_page_reload_brings_the_deck_back_to_the_slide_and_step_it_showed(studio_page):
    """SPEC story 5: the place survives any reload, the studio page's own (F5) included."""
    page = studio_page
    go_slide(page, 13, 2)
    page.reload()
    expect(page.locator("body[data-ready]")).to_be_attached()

    def place():
        s = page.evaluate("() => studio.deck.win().deck?.state()")
        return s and (s["slide"], s["fragment"])
    wait_until(lambda: place() == (13, 2), message="the deck back at slide 13, step 2")
