"""Seguir o agente in a project made by Deck Studio (bug of 2026-11-04, found by the recorded end-to-end test): such a
project has no part builds, so every edit reloads the deck page, and the studio then put the deck back where it was,
undoing the move to the edited slide."""
import json
import tempfile
from pathlib import Path

import pytest
from playwright.sync_api import expect

from deck_studio.templates import fill_template
from tests.e2e.conftest import built, deck_of, deck_state, go_slide, open_studio, run_studio
from tests.e2e.test_autonomo_seguir import SLIDES
from tests.helpers.kit_copy import PREFIX, remove_kit_copy


@pytest.fixture(scope="module")
def project():
    kit = Path(tempfile.mkdtemp(prefix=PREFIX))  # remove_kit_copy deletes it
    try:
        fill_template(kit, {"TITLE": "Projeto", "LANG": "pt-BR", "LANGUAGE": "Português (Brasil)",
                            "PDF": "context/a.pdf", "SLUG": "projeto"})
        (kit / "studio.json").write_text(json.dumps({"title": "Projeto", "format": "html", "language": "pt"}),
                                         encoding="utf-8")
        (kit / "deck/src/slides/99-pedido.html").write_text(SLIDES, encoding="utf-8")
        with run_studio(kit=kit) as s:
            yield s
    finally:
        remove_kit_copy(kit)


def test_following_survives_the_deck_reload_of_a_project(project, page, api):
    open_studio(page, project)
    built(project, api)
    go_slide(page, 1)
    page.get_by_role("textbox", name="Mensagem").fill("#scenario:follow-edit")
    page.get_by_role("textbox", name="Mensagem").press("Enter")
    expect(deck_of(page).locator(".studio-flash")).to_have_text("Caixa seguida", timeout=30_000)
    target = deck_of(page).locator("html").evaluate(
        "() => [...document.querySelectorAll('section.slide')].findIndex((s) => s.id === 's991') + 1")
    page.wait_for_timeout(800)  # past the studio's own restore of the place
    state = deck_state(page)
    assert (state["slide"], state["fragment"]) == (target, 1)
