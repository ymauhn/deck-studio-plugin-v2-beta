"""Pedido 2 (2026-11-04), the copy layout: a kit with no Portuguese tree (deck/src-pt), where the agent's translation
makes deck/src/i18n/pt/ and the switch copies it in. Tests run in order: the copy appears after the first ones.
The tree layout (NEXUS-GO's deck/src-pt) is in test_language_tree.py."""
import shutil

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import built, deck_of, run_studio, wait_until
from tests.helpers.kit_copy import make_kit_copy, remove_kit_copy


@pytest.fixture(scope="module")
def studio():
    kit = make_kit_copy()
    shutil.rmtree(kit / "deck" / "src-pt", ignore_errors=True)
    try:
        with run_studio(kit=kit) as s:
            yield s
    finally:
        remove_kit_copy(kit)

EN_TEXT = "Network-Extended Unified Sequence Embeddings"
PT_TEXT = "Embeddings de Sequência Unificados e Estendidos por Rede"


def conversation(page):
    return page.get_by_role("log", name="Conversa")


def answers(page):
    return conversation(page).get_by_role("article", name="Claude")


def switch(page):
    return page.get_by_role("radiogroup", name="Idioma do deck")


def slides(studio):
    return studio.kit / "deck" / "src" / "slides"


@pytest.fixture(scope="module")
def original(studio):
    """The English slides as the kit copy had them, by file name."""
    return {f.name: f.read_bytes() for f in slides(studio).glob("*.html")}


def test_the_deck_starts_in_english_with_portuguese_still_to_translate(studio, studio_page, api, original):
    page = studio_page
    expect(switch(page).get_by_role("radio", name="Inglês")).to_have_attribute("aria-checked", "true")
    expect(switch(page).get_by_role("radio", name="Português")).to_be_disabled()
    expect(page.get_by_role("button", name="Traduzir para português")).to_be_visible()
    r = api.post(f"{studio.base}/api/language", headers=studio.headers, data={"lang": "pt"})
    assert r.status == 400 and "Gere a tradução primeiro" in r.json()["message"]
    assert api.post(f"{studio.base}/api/language", headers=studio.headers, data={"lang": "fr"}).status == 400


def test_traduzir_asks_the_agent_for_the_portuguese_copy_in_the_chat(studio_page):
    page = studio_page
    page.get_by_role("button", name="Traduzir para português").click()
    asked = conversation(page).get_by_role("article", name="Você").last
    expect(asked).to_contain_text("Traduza o deck para português")
    expect(asked).to_contain_text("deck/src/i18n/pt/")
    expect(answers(page).last).to_have_text("ok")


def test_the_switch_shows_the_portuguese_copy_and_comes_back_to_the_same_english_bytes(studio, studio_page, api,
                                                                                         original):
    page = studio_page
    pt = studio.kit / "deck" / "src" / "i18n" / "pt"  # what the agent's translation leaves
    pt.mkdir(parents=True)
    for name, data in original.items():
        (pt / name).write_bytes(data.replace(EN_TEXT.encode(), PT_TEXT.encode()))
    page.reload()
    portuguese = switch(page).get_by_role("radio", name="Português")
    expect(portuguese).to_be_enabled()

    portuguese.click()
    expect(portuguese).to_have_attribute("aria-checked", "true")
    # English is the base language: the agent is never asked to translate back to it
    expect(page.get_by_role("button", name="Traduzir para inglês")).to_be_hidden()
    expect(deck_of(page).get_by_text(PT_TEXT)).to_be_visible()
    built(studio, api)
    assert PT_TEXT in (slides(studio) / "00-opening.html").read_text(encoding="utf-8")
    english = studio.kit / "deck" / "src" / "i18n" / "en"
    assert {f.name: f.read_bytes() for f in english.glob("*.html")} == original
    assert (studio.kit / "deck" / "src" / "i18n" / "active.txt").read_text(encoding="utf-8") == "pt"

    # the agent hears that the slides on screen are the Portuguese ones
    page.get_by_role("textbox", name="Mensagem").fill("#scenario:message")
    page.get_by_role("textbox", name="Mensagem").press("Enter")
    expect(answers(page).last).to_contain_text("now the Brazilian Portuguese version of the deck")

    switch(page).get_by_role("radio", name="Inglês").click()
    expect(switch(page).get_by_role("radio", name="Inglês")).to_have_attribute("aria-checked", "true")
    expect(deck_of(page).get_by_text(EN_TEXT)).to_be_visible()
    built(studio, api)
    assert {f.name: f.read_bytes() for f in slides(studio).glob("*.html")} == original


def test_the_language_does_not_change_while_a_request_runs(studio, studio_page, api):
    page = studio_page
    page.get_by_role("textbox", name="Mensagem").fill("#scenario:slow")
    page.get_by_role("textbox", name="Mensagem").press("Enter")
    wait_until(lambda: api.get(f"{studio.base}/api/status", headers=studio.headers).json()["busy"], 10, "the turn")
    expect(switch(page).get_by_role("radio", name="Português")).to_be_disabled()
    r = api.post(f"{studio.base}/api/language", headers=studio.headers, data={"lang": "pt"})
    assert r.status == 409
    expect(answers(page).last).to_have_text("Pronto, terminei.")
    expect(switch(page).get_by_role("radio", name="Português")).to_be_enabled()


def test_the_beamer_view_hides_the_language_switch(studio_page):
    page = studio_page
    page.evaluate("() => studio.mode.set('beamer')")
    expect(switch(page)).to_be_hidden()
    page.evaluate("() => studio.mode.set('html')")
    expect(switch(page)).to_be_visible()

