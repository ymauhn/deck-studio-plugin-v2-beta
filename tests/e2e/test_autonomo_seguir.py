"""Feedback of 2026-11-04: at the Autônomo level the author's real flow (read notes outside the kit, edit a slide,
build EN and PT, run the QA) shows no approval card; and "Seguir o agente" takes the deck to the slide of each edit,
flashes the changed box, and stops when the author moves the deck by hand, until the next request."""
import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import built, deck_of, deck_state, go_slide, run_studio
from tests.helpers.kit_copy import make_kit_copy, remove_kit_copy

SLIDES = """<section class="slide" id="s990" data-part="Pedido">
<h2 class="title">Pedido</h2>
<div class="bd"><p class="lead col-w">Texto antigo do pedido</p></div>
<aside class="notes"><p>Teste.</p></aside>
</section>
<section class="slide" id="s991" data-part="Pedido">
<h2 class="title">Seguir</h2>
<div class="bd"><p class="lead col-w">Primeira linha</p>
<p class="lead col-w f" data-f="1">Caixa a seguir</p></div>
<aside class="notes"><p>Teste.</p></aside>
</section>
"""


@pytest.fixture(scope="module")
def studio():
    kit = make_kit_copy()
    (kit / "deck" / "src" / "slides" / "99-pedido.html").write_text(SLIDES, encoding="utf-8")
    notes = kit.parent / "notas-do-pedido-e2e.md"  # outside the kit: ../ from it
    notes.write_text("# Notas do orientador\n\n- Um item por passo.\n", encoding="utf-8")
    try:
        with run_studio(kit=kit) as s:
            yield s
    finally:
        notes.unlink(missing_ok=True)
        remove_kit_copy(kit)


@pytest.fixture
def auto(studio, api):
    api.post(f"{studio.base}/api/settings", headers=studio.headers, data={"autonomy": "auto"})
    yield
    api.post(f"{studio.base}/api/settings", headers=studio.headers, data={"autonomy": "deck"})


def send(page, text):
    page.get_by_role("textbox", name="Mensagem").fill(text)
    page.get_by_role("textbox", name="Mensagem").press("Enter")


def answers(page):
    return page.get_by_role("log", name="Conversa").get_by_role("article", name="Claude")


def follow_button(page):
    return page.get_by_role("button", name="Seguir o agente")


def index_of(page, sid):
    return deck_of(page).locator("html").evaluate(
        f"() => [...document.querySelectorAll('section.slide')].findIndex((s) => s.id === '{sid}') + 1")


def test_the_pedido_flow_runs_without_any_card_at_autonomo(studio, studio_page, auto):
    page = studio_page
    send(page, "#scenario:pedido-autonomo")
    expect(answers(page).last).to_have_text("Pronto.", timeout=30_000)
    expect(page.get_by_role("article", name="Aprovação: Bash")).to_have_count(0)
    expect(page.locator("article.approval")).to_have_count(0)
    tools = page.get_by_role("log", name="Conversa").locator("article").filter(has_text="notas-do-pedido-e2e.md")
    expect(tools.first).to_be_visible()  # the read outside the kit happened, with no card
    assert "Texto novo do pedido" in (studio.kit / "deck" / "src" / "slides" / "99-pedido.html").read_text(encoding="utf-8")


def test_follow_is_on_by_default_and_goes_to_the_edited_box(studio, studio_page, api):
    page = studio_page
    expect(follow_button(page)).to_have_attribute("aria-pressed", "true")
    go_slide(page, 1)
    send(page, "#scenario:follow-edit")
    # the deck moves to s991 at its last step, and the edited box flashes
    expect(deck_of(page).locator(".studio-flash")).to_have_text("Caixa seguida", timeout=20_000)
    slide = index_of(page, "s991")
    state = deck_state(page)
    assert (state["slide"], state["fragment"]) == (slide, 1)
    expect(answers(page).last).to_have_text("Editei a caixa.")
    expect(deck_of(page).locator(".studio-flash")).to_have_count(0, timeout=5_000)


def test_moving_the_deck_by_hand_stops_following_until_the_next_request(studio, studio_page, api):
    page = studio_page
    built(studio, api)
    go_slide(page, 1)
    send(page, "#scenario:slow")
    expect(page.get_by_role("button", name="Parar")).to_be_visible()
    deck_of(page).locator("#deck").click(position={"x": 800, "y": 600})  # the author moves on
    page.keyboard.press("ArrowRight")
    assert deck_state(page)["slide"] > 1
    expect(follow_button(page)).to_have_attribute("aria-pressed", "false")
    expect(answers(page).last).to_have_text("Pronto, terminei.")
    # the next request follows again
    go_slide(page, 1)
    src = studio.kit / "deck" / "src" / "slides" / "99-pedido.html"
    src.write_text(src.read_text(encoding="utf-8").replace("Caixa seguida", "Caixa a seguir"), encoding="utf-8")
    built(studio, api)
    send(page, "#scenario:follow-edit")
    expect(follow_button(page)).to_have_attribute("aria-pressed", "true")
    expect(deck_of(page).locator(".studio-flash")).to_have_text("Caixa seguida", timeout=20_000)


def test_the_button_turns_following_off_and_that_stays_across_requests(studio, studio_page, api):
    page = studio_page
    follow_button(page).click()
    expect(follow_button(page)).to_have_attribute("aria-pressed", "false")
    go_slide(page, 1)
    src = studio.kit / "deck" / "src" / "slides" / "99-pedido.html"
    src.write_text(src.read_text(encoding="utf-8").replace("Caixa seguida", "Caixa a seguir"), encoding="utf-8")
    built(studio, api)
    send(page, "#scenario:follow-edit")
    expect(answers(page).last).to_have_text("Editei a caixa.", timeout=20_000)
    expect(follow_button(page)).to_have_attribute("aria-pressed", "false")
    assert deck_state(page)["slide"] == 1
    expect(deck_of(page).locator(".studio-flash")).to_have_count(0)
    follow_button(page).click()
    expect(follow_button(page)).to_have_attribute("aria-pressed", "true")
