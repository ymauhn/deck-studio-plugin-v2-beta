"""Ir para o slide (feedback of 2026-11-04): a field in the top bar takes the deck to slide N or to a backup slide
(B9), shows the total, and works the same with the Portuguese deck."""
from playwright.sync_api import expect

from tests.e2e.conftest import built, deck_state


def field(page):
    return page.get_by_role("textbox", name="Ir para o slide")


def go(page, text):
    field(page).fill(text)
    field(page).press("Enter")


def test_the_field_shows_the_total_and_goes_to_a_slide(studio_page):
    page = studio_page
    state = deck_state(page)
    expect(page.locator("#goto-total")).to_have_text(f"de {state['total']} + {state['backups']} de reserva")
    go(page, "7")
    assert deck_state(page)["label"] == "7" and deck_state(page)["fragment"] == 0
    expect(field(page)).to_have_value("")
    page.keyboard.press("ArrowRight")  # the deck has the keyboard again: the next step or slide
    after = deck_state(page)
    assert (after["slide"], after["fragment"]) != (7, 0)


def test_a_backup_slide_goes_by_its_label(studio_page):
    page = studio_page
    go(page, "b2")
    assert deck_state(page)["label"] == "B2"
    go(page, "B1")
    assert deck_state(page)["label"] == "B1"


def test_a_slide_the_deck_does_not_have_says_so(studio_page):
    page = studio_page
    go(page, "1")
    go(page, "999")
    expect(page.get_by_role("status").or_(page.get_by_role("alert")).filter(has_text="não tem o slide 999")).to_be_visible()
    assert deck_state(page)["label"] == "1"


def test_it_works_with_the_portuguese_deck(studio, studio_page, api):
    page = studio_page
    page.get_by_role("radiogroup", name="Idioma do deck").get_by_role("radio", name="Português").click()
    built(studio, api)
    expect(page.get_by_role("radiogroup", name="Idioma do deck").get_by_role("radio", name="Português")).to_have_attribute(
        "aria-checked", "true")
    page.wait_for_function("() => document.getElementById('goto-total').textContent.startsWith('de ')")
    go(page, "5")
    assert deck_state(page)["label"] == "5"
    expect(page.locator("#goto-total")).to_contain_text("de ")
