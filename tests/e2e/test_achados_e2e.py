"""The findings of the recorded end-to-end test (2026-11-04), in the browser: an approval card says it is denied after
2 minutes without an answer; in a direct edit, End goes after an inline formula."""
import json
import tempfile
from pathlib import Path

import pytest
from playwright.sync_api import expect

from deck_studio.templates import fill_template
from tests.e2e.conftest import built, deck_of, go_slide, open_studio, run_studio
from tests.helpers.kit_copy import PREFIX, remove_kit_copy

FORMULA = """<section class="slide" id="s02" data-part="Método">
<h2 class="title">Só a massa mínima</h2>
<div class="bd"><ul class="b col-w"><li>Só se mede <i>M</i><sub>p</sub> sin <i>i</i></li></ul></div>
<aside class="notes"><p>Teste. (p. 1)</p></aside>
</section>
"""


@pytest.fixture(scope="module")
def project():
    kit = Path(tempfile.mkdtemp(prefix=PREFIX))  # remove_kit_copy deletes it
    try:
        fill_template(kit, {"TITLE": "Projeto", "LANG": "pt-BR", "LANGUAGE": "Português (Brasil)",
                            "PDF": "context/a.pdf", "SLUG": "projeto"})
        (kit / "studio.json").write_text(json.dumps({"title": "Projeto", "format": "html", "language": "pt"}),
                                         encoding="utf-8")
        (kit / "deck/src/slides/01-formula.html").write_text(FORMULA, encoding="utf-8")
        with run_studio(kit=kit) as s:
            yield s
    finally:
        remove_kit_copy(kit)


def test_a_card_says_it_is_denied_after_two_minutes(project, page):
    open_studio(page, project)
    page.get_by_role("textbox", name="Mensagem").fill("#scenario:bash")  # npm run lint: asks at the default level
    page.get_by_role("textbox", name="Mensagem").press("Enter")
    card = page.get_by_role("article", name="Aprovação: Bash")
    expect(card).to_contain_text("Sem resposta em 2 min, o pedido é negado e o agente segue sem ele.")
    card.get_by_role("button", name="Negar").click()
    expect(card.get_by_role("button")).to_have_count(0)


def test_end_goes_after_the_inline_formula(project, page, api):
    open_studio(page, project)
    built(project, api)
    go_slide(page, 2)
    deck = deck_of(page)
    deck.get_by_text("Só se mede").dblclick(position={"x": 10, "y": 10})
    editor = deck.locator(".studio-editing")
    expect(editor).to_be_visible()
    editor.press("End")
    editor = deck.locator(".studio-editing")  # the editor moved to the end of the box
    expect(editor).to_be_focused()
    page.keyboard.type(" (editado à mão)")
    page.keyboard.press("Enter")
    expect(page.get_by_role("article").filter(has_text="Texto editado em")).to_be_visible(timeout=20_000)
    source = (project.kit / "deck/src/slides/01-formula.html").read_text(encoding="utf-8")
    assert "<li>Só se mede <i>M</i><sub>p</sub> sin <i>i</i> (editado à mão)</li>" in source
