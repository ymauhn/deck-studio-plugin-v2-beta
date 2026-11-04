"""The agent edit loop with the fake agent: guard, history turns, rebuilds, deck tools and tool cards."""
import base64
import json
import re

from playwright.sync_api import expect

from tests.e2e.conftest import built, deck_of, go_slide, slide_and_step, status_of


def composer(page):
    return page.get_by_role("textbox", name="Mensagem")


def conversation(page):
    return page.get_by_role("log", name="Conversa")


def answers(page):
    return conversation(page).get_by_role("article", name="Claude")


def send(page, text):
    composer(page).fill(text)
    composer(page).press("Enter")


def catch_turn_end(page):
    """From now on, window.turnEnd resolves to the next turn-end event."""
    page.evaluate("""() => { window.turnEnd = new Promise((resolve) => {
        const off = studio.on('chat', (e) => { if (e.kind === 'turn-end') { off(); resolve(e); } });
    }); }""")


def turn_end(page):
    return page.evaluate("() => window.turnEnd")


def test_an_allowed_edit_rebuilds_and_reloads_the_deck_in_place_and_the_turn_end_lists_the_file(studio, studio_page):
    page = studio_page
    # following the agent (on by default) would show the edited slide at its last step: off, the deck stays put
    page.get_by_role("button", name="Seguir o agente").click()
    go_slide(page, 13, 3)
    catch_turn_end(page)
    send(page, "#scenario:edit-slide")
    expect(answers(page).last).to_have_text("Pronto.")
    assert turn_end(page)["files"] == ["deck/src/slides/03-data.html"]
    assert "Mean labels per protein" in (studio.kit / "deck/src/slides/03-data.html").read_text(encoding="utf-8")

    expect(deck_of(page).locator("#s13")).to_contain_text("Mean labels per protein")
    assert slide_and_step(page) == (13, 3)


def test_a_build_error_after_an_edit_goes_back_to_the_agent_in_the_same_request(studio, studio_page, api):
    page = studio_page
    send(page, "#scenario:break-build")
    expect(answers(page)).to_have_count(2)
    expect(answers(page).first).to_contain_text("Contexto: The deck build failed after this edit")
    expect(answers(page).first).to_contain_text("missing assets: img/no-such-image.png")
    # a good build adds nothing
    expect(answers(page).last).to_have_text(re.compile(r"^Contexto depois de corrigir:\s*$"))
    assert built(studio, api)["ok"] is True


SELECTED_TEX = {"kind": "tex", "file": "beamer/academico/nexus-go-academic.tex", "frame": {"start": 40, "end": 58},
                "line": 44, "text": "Label matrix density", "page": 7}


def test_the_agent_gets_every_selection_field_including_a_comment_and_a_tex_frame(studio_page):
    page = studio_page
    items = [
        {"slideId": "s13", "slide": 13, "step": 3, "part": "03-data.html",
         "loc": {"file": "deck/src/slides/03-data.html", "line": 9, "col": 5}, "tag": "li", "kind": "text",
         "comment": "mais curto, por favor"},
        SELECTED_TEX,
    ]
    page.evaluate("(items) => studio.chat.send('#scenario:selection-raw', { selection: items })", items)
    expect(answers(page).last).to_contain_text("Recebi: ")
    assert json.loads(answers(page).last.inner_text().removeprefix("Recebi: ")) == items


def box(slide, step, line, col=5):
    return {"slideId": f"s{slide}", "slide": slide, "step": step, "part": "03-data.html",
            "loc": {"file": "deck/src/slides/03-data.html", "line": line, "col": col}, "tag": "li", "kind": "text"}


def test_a_message_with_a_selection_carries_an_image_of_each_selected_slide_with_its_boxes_outlined(studio_page):
    """SPEC story 15: the agent sees what the author saw, one image per slide and step of the selection, its boxes
    outlined; a box the deck no longer has is named, and a TeX frame or a message without a selection adds none."""
    page = studio_page
    items = [box(13, 3, 9), box(14, 1, 34), box(13, 3, 10), SELECTED_TEX, box(13, 3, 9, col=6)]
    page.evaluate("(items) => studio.chat.send('#scenario:images', { selection: items })", items)
    expect(answers(page).last).to_have_text(re.compile(
        r"^Imagens: Slide 13 \(s13\), step 3 of 3\. "
        r"Nothing has data-loc deck/src/slides/03-data\.html:9:6 on this deck\.\s+\[image/png 1600x900\]\s+"
        r"Slide 14 \(s14\), step 1 of 3\.\s+\[image/png 1600x900\]$"), timeout=30_000)

    send(page, "#scenario:images")
    expect(answers(page).last).to_have_text("Imagens: nenhuma")


def test_a_turn_that_ends_with_an_error_says_so_and_names_the_files_it_changed(studio, studio_page, api):
    page = studio_page
    catch_turn_end(page)
    send(page, "#scenario:fail")
    alert = page.get_by_role("alert")
    expect(alert.locator(":scope > p")).to_have_text(
        "O pedido terminou com um erro do Claude. Envie a mensagem de novo em alguns minutos. "
        "Ficaram alterados: deck/src/slides/03-data.html.")
    expect(alert.locator("details")).to_contain_text("a API respondeu 529 (sobrecarregada)")  # the CLI's own words
    assert turn_end(page)["files"] == ["deck/src/slides/03-data.html"]
    expect(conversation(page)).not_to_contain_text("não deveria aparecer")
    assert status_of(studio, api)["busy"] is False

    send(page, "#scenario:hello")  # the same session goes on
    expect(answers(page).last).to_have_text("Olá! Sou o agente de teste do Deck Studio.")


def test_a_turn_that_fails_during_a_tool_says_what_to_do_in_portuguese_with_the_detail_below_and_ends_its_card(
        studio, studio_page, api):
    """The SDK's reader died on a message over its buffer (2026-10-28): the author read raw SDK English, and the
    card of the tool it was running stayed blue, as if still running."""
    page = studio_page
    catch_turn_end(page)
    send(page, "#scenario:crash")
    alert = page.get_by_role("alert")
    expect(alert.locator(":scope > p")).to_have_text(
        "O agente parou com um erro inesperado. Envie a mensagem de novo para continuar. Nenhum arquivo foi alterado.")
    detail = alert.locator("details")
    expect(detail.locator("summary")).to_have_text("Detalhe técnico")
    expect(detail).to_contain_text(
        "CLIJSONDecodeError: Failed to decode JSON: JSON message exceeded maximum buffer size of 1048576 bytes")
    assert detail.evaluate("(d) => d.open") is False  # secondary: closed until the author opens it
    expect(tool_cards(page)).to_have_text(["Leu figura.png sem resultado"])
    expect(tool_cards(page).first).to_have_attribute("data-state", "stopped")
    assert turn_end(page)["files"] == []
    assert status_of(studio, api)["busy"] is False

    page.reload()  # the conversation comes back the same
    expect(page.locator("body[data-ready]")).to_be_attached()
    expect(tool_cards(page).first).to_have_attribute("data-state", "stopped")
    expect(page.get_by_role("article", name="Erro").locator("details")).to_contain_text("CLIJSONDecodeError")
    send(page, "#scenario:hello")  # a new session takes over
    expect(answers(page).last).to_have_text("Olá! Sou o agente de teste do Deck Studio.")


def test_interrupting_a_running_turn_ends_it_with_a_message_and_frees_the_studio(studio, studio_page, api):
    page = studio_page
    catch_turn_end(page)
    send(page, "#scenario:long")
    expect(answers(page).last).to_have_text("Vou demorar.")
    chat_id = page.evaluate("() => studio.chat.current().id")
    res = api.post(f"{studio.base}/api/chats/{chat_id}/interrupt", headers=studio.headers)
    assert res.status == 200

    expect(page.get_by_role("alert")).to_have_text("Pedido interrompido. Nenhum arquivo foi alterado.", timeout=5000)
    assert turn_end(page)["files"] == []
    assert status_of(studio, api)["busy"] is False
    send(page, "#scenario:hello")
    expect(answers(page).last).to_have_text("Olá! Sou o agente de teste do Deck Studio.")
    expect(conversation(page)).not_to_contain_text("não deveria aparecer")


def tool_cards(page):
    return conversation(page).get_by_role("article", name=re.compile("^Ferramenta"))


def test_each_tool_call_shows_a_compact_card_with_the_file_name_or_pattern_and_a_denial_says_why(studio_page):
    page = studio_page
    send(page, "#scenario:tools")
    expect(answers(page).last).to_have_text("Feito.")
    expect(tool_cards(page)).to_have_text([
        "Leu 03-data.html",
        "Listou deck/src/slides/*.html",
        "Buscou Labels per",
        "Escreveu notas.md",
        "Editou notas.md",
        "Escreveu x.txt negado: Escrita bloqueada: data/** é protegido.",
    ])
    expect(tool_cards(page).first.locator("code")).to_have_attribute("title", "deck/src/slides/03-data.html")
    expect(tool_cards(page).last).to_have_attribute("data-state", "denied")
    expect(tool_cards(page).first).to_have_attribute("data-state", "ok")


SELECTED = {"slideId": "s13", "slide": 13, "step": 3, "part": "03-data.html",
            "loc": {"file": "deck/src/slides/03-data.html", "line": 9, "col": 5}, "tag": "li", "kind": "text"}


def test_the_deck_tool_get_selection_returns_the_selection_sent_with_the_message(studio_page):
    page = studio_page
    page.evaluate("(item) => studio.chat.send('#scenario:get-selection', { selection: [item] })", SELECTED)
    expect(answers(page).last).to_contain_text("Seleção: ")
    assert json.loads(answers(page).last.inner_text().removeprefix("Seleção: ")) == [SELECTED]
    expect(tool_cards(page)).to_have_text(["Leu a seleção"])


def test_the_deck_tool_rebuild_deck_builds_and_reports_the_build(studio_page):
    page = studio_page
    send(page, "#scenario:rebuild")
    expect(answers(page).last).to_have_text(
        re.compile(r"^Resultado: The studio deck built without errors in \d+ ms\.$"))
    expect(tool_cards(page)).to_have_text(["Recompilou o deck"])


def test_the_deck_tool_screenshot_slide_returns_a_png_of_the_slide_at_1600x900(studio_page):
    page = studio_page
    send(page, "#scenario:screenshot")
    expect(answers(page).last).to_have_text(
        re.compile(r"^Vi: Slide 13 \(s13\), step 1 of 3\.\s+\[image/png 1600x900\]$"), timeout=30_000)
    expect(tool_cards(page)).to_have_text(["Viu o slide 13"])


def test_the_deck_tool_check_slide_reports_clipped_boxes_and_elements_outside_the_frame(studio_page):
    page = studio_page
    send(page, "#scenario:check")
    expect(answers(page).last).to_have_text("Desfeito.", timeout=30_000)
    expect(answers(page).first).to_have_text(
        "Antes: Slide 13 (s13), step 3 of 3: nothing clipped and nothing outside the 1600x900 frame.")
    after = answers(page).nth(1)
    expect(after).to_contain_text("Depois: Slide 13 (s13), step 3 of 3: 2 problems.")
    expect(after).to_contain_text(
        re.compile(r"clipped: div \(deck/src/slides/03-data\.html:2:\d+\) holds 200x\d+ in a 200x30 box"))
    expect(after).to_contain_text(
        re.compile(r"outside the frame: div \(deck/src/slides/03-data\.html:2:\d+\) at x \d+\.\.\d+"))
    expect(tool_cards(page).filter(has_text="Conferiu o slide")).to_have_count(2)


PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")


def test_the_deck_tool_add_image_copies_a_context_image_under_a_new_safe_name_and_gives_its_img_tag(
        studio, studio_page):
    page = studio_page
    context = studio.kit / "context"
    context.mkdir(exist_ok=True)
    (context / "Minha Figura Ção.PNG").write_bytes(PNG)
    (context / "foto.jpeg").write_bytes(PNG)
    (context / "notas.txt").write_text("notas", encoding="utf-8")
    catch_turn_end(page)
    send(page, "#scenario:add-image")
    expect(answers(page)).to_have_text([
        '1: Copied to deck/src/img/minha-figura-cao.png. Put it on a slide with '
        '<img src="img/minha-figura-cao.png" alt="..."> and a real alt text.',
        '2: Copied to deck/src/img/minha-figura-cao-2.png. Put it on a slide with '
        '<img src="img/minha-figura-cao-2.png" alt="..."> and a real alt text.',
        '3: Copied to deck/src/img/grafico-final.jpg. Put it on a slide with '
        '<img src="img/grafico-final.jpg" alt="..."> and a real alt text.',
        "4: Only png, jpg, webp or svg images can go on a slide; notas.txt is not one.",
        "5: The image must be a file in the context folder; ../tools/numbering.py is not.",
    ])
    images = studio.kit / "deck" / "src" / "img"
    assert [(images / f).read_bytes() for f in ("minha-figura-cao.png", "minha-figura-cao-2.png")] == [PNG, PNG]
    assert turn_end(page)["files"] == ["deck/src/img/minha-figura-cao.png", "deck/src/img/minha-figura-cao-2.png",
                                       "deck/src/img/grafico-final.jpg"]
    expect(tool_cards(page).first).to_have_text("Adicionou a imagem Minha Figura Ção.PNG")


def test_a_studio_error_while_checking_a_tool_call_denies_the_call(studio, studio_page):
    page = studio_page
    send(page, "#scenario:write-folder")  # the snapshot of a folder fails
    expect(answers(page).last).to_contain_text(
        "Resultado: PreToolUse:Write hook error: Erro do estúdio ao checar esta chamada:")
    assert (studio.kit / "deck" / "src" / "slides").is_dir()


def test_the_guard_denies_a_write_to_data_and_the_agent_gets_the_reason(studio, studio_page):
    page = studio_page
    send(page, "#scenario:write-data")
    expect(answers(page).last).to_have_text(
        "Resultado: PreToolUse:Write hook error: Escrita bloqueada: data/** é protegido.")
    assert not (studio.kit / "data" / "studio-test.txt").exists()


def test_an_approved_shell_command_rebuilds_the_deck_so_the_screen_and_the_agent_see_what_it_changed(
        studio, studio_page):
    """Undo does not cover a shell command, but the deck must not go stale after one: what an approved command
    changed in the deck sources reaches the screen and the agent's next look at the slide."""
    page = studio_page
    part = studio.kit / "deck/src/slides/03-data.html"
    source = part.read_bytes()
    send(page, "#scenario:shell-edit")
    card = page.get_by_role("article", name="Aprovação: PowerShell")
    expect(card).to_be_visible()
    title = b'<h2 class="title">STRING v11.5: one aggregated network</h2>'
    box = b'<div style="width:200px;height:30px;overflow:hidden">long text long text long text long text</div>'
    part.write_bytes(source.replace(title, title + box, 1))  # what the command does once it runs (the fake runs none)
    try:
        card.get_by_role("button", name="Permitir").click()
        answer = answers(page).last  # the check's "- " line shows as a list item
        expect(answer.locator(":scope > p")).to_have_text(re.compile(
            r"^Depois do comando: Slide 14 \(s14\), step (\d+) of \1: 1 problem\.$"), timeout=30_000)
        expect(answer.locator("li")).to_have_text(re.compile(
            r"^clipped: div \(deck/src/slides/03-data\.html:\d+:\d+\) holds 200x\d+ in a 200x30 box$"))
        expect(deck_of(page).locator("#s14")).to_contain_text("long text long text")
    finally:
        part.write_bytes(source)


def test_the_slide_checks_and_screenshots_load_no_local_file_but_the_deck_itself(studio, studio_page, tmp_path):
    """A slide may point at any file on the disk (an image, a document in a frame); the renderer behind
    screenshot_slide and check_slide loads the deck alone, so the agent never sees a file outside the kit."""
    page = studio_page
    private = tmp_path / "private.svg"  # outside the kit: if it loads, it lands outside the slide's frame
    private.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300">'
                       '<rect width="400" height="300" fill="#c00"/></svg>', encoding="utf-8")
    part = studio.kit / "deck/src/slides/00-opening.html"
    source = part.read_bytes()
    title = b'<h2 class="title">Roadmap</h2>'
    part.write_bytes(source.replace(title, title + (
        f'<img src="{private.as_uri()}" alt="" style="position:absolute;left:1500px;top:20px">'
        f'<object data="{private.as_uri()}" type="image/svg+xml" style="position:absolute;left:1500px;top:400px">'
        '</object>').encode(), 1))
    try:
        send(page, "#scenario:rebuild-check")
        expect(answers(page).last).to_have_text(re.compile(
            r"^Conferi: Slide 2 \(s02\), step (\d+) of \1: nothing clipped and nothing outside the 1600x900 frame\.$"),
            timeout=30_000)
    finally:
        part.write_bytes(source)
