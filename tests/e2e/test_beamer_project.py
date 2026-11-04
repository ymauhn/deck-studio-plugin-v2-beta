"""A Beamer project ([beamer-tools]): a studio whose studio.json names the beamer format compiles its deck
(studio.project.beamerStart) from the start and opens in Beamer mode on it; the agent's deck tools compile_beamer and
screenshot_beamer_page compile and show that deck as the Beamer view does."""
import json
import re
import tempfile
import zipfile
from pathlib import Path

import pymupdf
import pytest
from playwright.sync_api import expect

from deck_studio.templates import fill_template
from tests.e2e.conftest import open_studio, run_studio, wait_until
from tests.e2e.test_agent_loop import answers, catch_turn_end, conversation, send, turn_end
from tests.e2e.test_beamer import compile_errors, compiled, mode_button, page_image, projects
from tests.helpers.kit_copy import PREFIX, remove_kit_copy

START = "beamer/apresentacao/apresentacao.tex"
# three frames, the second one broken: TeX reports an error in a frame on its \end{frame} line, line 10 here
BROKEN = r"""\documentclass[aspectratio=169]{beamer}
\begin{document}

\begin{frame}{Fine}
  All good here.
\end{frame}

\begin{frame}{Broken}
  \nosuchmacro
\end{frame}

\begin{frame}{After}
  Still compiles.
\end{frame}

\end{document}
"""


@pytest.fixture(scope="module")
def studio():
    """A studio on the filled project template with a studio.json of the beamer format, as a Beamer import has."""
    kit = Path(tempfile.mkdtemp(prefix=PREFIX))  # remove_kit_copy deletes it
    try:
        fill_template(kit, {"TITLE": "Aula de Redes", "LANG": "pt-BR", "LANGUAGE": "Português (Brasil)",
                            "PDF": "context/aula.pdf", "SLUG": "aula-de-redes"})
        (kit / "studio.json").write_text(json.dumps({"title": "Aula de Redes", "format": "beamer", "language": "pt"}),
                                         encoding="utf-8")
        with run_studio(kit=kit) as s:
            yield s
    finally:
        remove_kit_copy(kit)


def beamer_projects(studio, api):
    return api.get(f"{studio.base}/api/beamer/projects", headers=studio.headers).json()


def test_a_beamer_project_compiles_its_deck_at_start_and_opens_in_beamer_mode_on_it(studio, api, page):
    # before any page opens: the studio has compiled the template's deck, its title and outline frames
    [deck] = wait_until(lambda: [p for p in beamer_projects(studio, api) if p["last"]], 90, "the first compile")
    assert (deck["rel"], deck["last"]["ok"], deck["view"]["pages"]) == (START, True, 2)

    open_studio(page, studio)
    expect(mode_button(page, "Beamer")).to_have_attribute("aria-pressed", "true")
    assert page.evaluate("() => studio.mode.get()") == "beamer"
    expect(projects(page)).to_be_hidden()  # the deck itself, not the list of projects
    expect(page.locator(".beamer-title")).to_have_text(START)
    compiled(page)
    expect(page_image(page)).to_have_accessible_name("Página 1 de 2")


def test_the_files_pane_opens_on_the_decks_folder_with_its_start_file_selected(studio_page):
    """Not on the HTML template, which a Beamer project leaves as it is: the deck's folder comes first and open, its
    main .tex marked as the current file, and the template's slides stay shut."""
    pane = studio_page.get_by_role("region", name="Arquivos")
    expect(pane.locator("summary").first).to_have_text("beamer/apresentacao/")
    deck = pane.get_by_role("list", name="beamer/apresentacao")
    expect(deck.get_by_role("button", name="apresentacao.tex")).to_have_attribute("aria-current", "true")
    expect(pane.locator("[aria-current]")).to_have_count(1)
    expect(pane.get_by_role("list", name="deck/src/slides")).to_have_count(0)


def test_compile_beamer_compiles_the_deck_as_the_view_does_and_names_each_errors_file_and_line(studio, studio_page):
    page = studio_page
    compiled(page)
    (studio.kit / START).write_text(BROKEN, encoding="utf-8")
    page.evaluate("""() => { window.seen = []; studio.on('beamer', (e) => window.seen.push(`${e.scope} ${e.state}`));
        studio.on('chat', (e) => e.kind === 'turn-end' && window.seen.push('turn-end')); }""")
    catch_turn_end(page)
    send(page, "#scenario:beamer-compile")
    turn_end(page)
    assert json.loads(answers(page).last.inner_text().removeprefix("Resultado: ")) == {
        "ok": False, "pages": 3, "errors": [{"file": START, "line": 10, "message": "Undefined control sequence."}],
        "boxes": []}
    expect(conversation(page).get_by_role("article", name="Ferramenta: Compilou o Beamer")).to_have_attribute(
        "data-state", "error")
    # the Beamer view's own compile, while the agent works: the screen shows that deck, with its error
    assert page.evaluate("() => window.seen") == ["full running", "full error", "turn-end"]
    expect(page_image(page)).to_have_accessible_name("Página 1 de 3")
    expect(compile_errors(page)).to_have_text("apresentacao.tex:10 Undefined control sequence.")


# a frame too tall for its page, a frame in an \input file too wide, a line half a point too wide (under 1 pt: it does
# not count) and a box TeX finds underfull. TeX reports a box inside a frame on that frame's \end{frame} line
BOXES = r"""\documentclass[aspectratio=169]{beamer}
\begin{document}

\begin{frame}{Too tall}
  \rule{1pt}{1.2\textheight}
\end{frame}

\input{parte 2.tex}

\begin{frame}{Half a point}
  \rule{\dimexpr\textwidth+0.5pt}{1pt}
\end{frame}

\begin{frame}{Loose}
  \hbox to \textwidth{a b}
\end{frame}

\end{document}
"""
PART = r"""% the second part of the talk
\begin{frame}{Too wide}
  \rule{\dimexpr\textwidth+30pt}{1pt}
\end{frame}
"""


def test_compile_beamer_also_lists_each_box_over_1_pt_with_its_file_line_and_size(studio, studio_page):
    """A figure at 0.7\\textheight with a two-line caption runs a few points into the footline: the agent sees it in
    the result, not only on the page."""
    page = studio_page
    (studio.kit / "beamer/apresentacao/parte 2.tex").write_text(PART, encoding="utf-8")
    (studio.kit / START).write_text(BOXES, encoding="utf-8")
    catch_turn_end(page)
    send(page, "#scenario:beamer-compile")
    turn_end(page)
    result = json.loads(answers(page).last.inner_text().removeprefix("Resultado: "))
    assert (result["ok"], result["errors"]) == (True, [])
    boxes = result["boxes"]
    assert [(b["file"], b["line"]) for b in boxes] == [
        (START, 6), ("beamer/apresentacao/parte 2.tex", 4), (START, 16)]
    assert re.fullmatch(r"Overfull \\vbox \(\d+\.\d+pt too high\)", boxes[0]["message"]), boxes[0]
    assert [b["message"] for b in boxes[1:]] == ["Overfull \\hbox (30.0pt too wide)", "Underfull \\hbox (badness 10000)"]


def test_screenshot_beamer_page_gives_a_page_of_the_last_compile_1600_px_wide(studio, studio_page):
    page = studio_page
    (studio.kit / START).write_text(BROKEN.replace(r"\nosuchmacro", "Fixed."), encoding="utf-8")
    catch_turn_end(page)
    send(page, "#scenario:beamer-page")
    turn_end(page)
    expect(answers(page).last).to_have_text(re.compile(
        r"^Vi: Page 3 of 3 of beamer/apresentacao/apresentacao\.tex\.\s+\[image/png 1600x900\]$"))
    expect(conversation(page).get_by_role("article", name="Ferramenta: Viu uma página do Beamer")).to_have_attribute(
        "data-state", "ok")


def test_abrir_pdf_in_the_beamer_bar_opens_the_pdf_of_the_decks_last_compile(studio, page, api):
    # a Beamer project's PDF is its Beamer deck's: Exportar PDF would print the HTML deck, which it does not have
    (studio.kit / START).write_text(BROKEN.replace(r"\nosuchmacro", "Opened as a PDF."), encoding="utf-8")
    open_studio(page, studio)  # its deck changed: it compiles on open
    compiled(page)
    link = page.locator(".beamer-bar").get_by_role("link", name="Abrir PDF")
    expect(link).to_have_attribute("target", "_blank")
    pdf = api.get(studio.base + link.get_attribute("href"), headers=studio.headers)
    assert (pdf.status, pdf.headers["content-type"]) == (200, "application/pdf")
    with pymupdf.open(stream=pdf.body(), filetype="pdf") as d:
        assert d.page_count == 3
        assert "Opened as a PDF." in d[1].get_text()


RICH = r"""\documentclass[aspectratio=169]{beamer}
\usetheme{Madrid}
\graphicspath{{figures/}{logos/}}
\begin{document}
\begin{frame}{Tabela}
  \input{tables.tex}
\end{frame}
\begin{frame}{Figura}
  \includegraphics[width=3cm]{grafico}\quad\includegraphics[width=1cm]{logo}
  Como em \cite{luque2026}.
\end{frame}
\begin{frame}{Refer\^encias}
  \bibliographystyle{plain}
  \bibliography{refs}
\end{frame}
\end{document}
"""


def png(path, rgb):
    doc = pymupdf.open()
    page = doc.new_page(width=40, height=30)
    page.draw_rect(page.rect, color=rgb, fill=rgb)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(page.get_pixmap().tobytes("png"))


def test_exportar_para_o_overleaf_zips_what_the_deck_reads_with_the_last_pdf_and_a_copy_compiles_alone(studio, page,
                                                                                                         api):
    deck = studio.kit / "beamer" / "apresentacao"
    (deck / "apresentacao.tex").write_text(RICH, encoding="utf-8")
    (deck / "tables.tex").write_text("\\begin{tabular}{lr} a & 1,5 \\\\ b & 2,0 \\end{tabular}\n", encoding="utf-8")
    (deck / "refs.bib").write_text("@article{luque2026, author={Luque, R. and Standing, M.}, title={Radial Velocity}, "
                                   "journal={arXiv}, year={2026}}\n", encoding="utf-8")
    png(deck / "figures" / "grafico.png", (0.2, 0.4, 0.8))
    png(deck / "logos" / "logo.png", (0.9, 0.4, 0.1))
    (deck / "figures" / "nao-usada.png").write_bytes((deck / "figures" / "grafico.png").read_bytes())
    open_studio(page, studio)  # its deck changed: it compiles on open
    compiled(page)
    bar = page.locator(".beamer-bar")
    bar.get_by_role("button", name="Exportar para o Overleaf").click()
    expect(bar.locator(".beamer-export")).to_have_text(
        "exports/apresentacao-overleaf.zip: 7 arquivos; uma cópia compilou sozinha, sem nenhum [?].", timeout=180_000)
    expect(bar.get_by_role("button", name="Abrir pasta")).to_be_visible()  # opens Explorer: not clicked here
    with zipfile.ZipFile(studio.kit / "exports" / "apresentacao-overleaf.zip") as z:
        assert sorted(z.namelist()) == ["apresentacao.pdf", "apresentacao.tex", "figures/grafico.png", "latexmkrc",
                                        "logos/logo.png", "refs.bib", "tables.tex"]
        zipped_pdf = z.read("apresentacao.pdf")
    # the PDF that goes with it is the last compile's, the one Abrir PDF opens
    href = bar.get_by_role("link", name="Abrir PDF").get_attribute("href")
    assert zipped_pdf == api.get(studio.base + href, headers=studio.headers).body()


def test_an_agent_edit_to_the_tex_recompiles_the_deck_while_its_turn_still_runs(studio, page):
    # the author watches the deck being written: each .tex edit compiles it, not only the end of the turn
    (studio.kit / START).write_text(BROKEN.replace(r"\nosuchmacro", "Fixed."), encoding="utf-8")
    open_studio(page, studio)
    compiled(page)
    page.evaluate("""() => { window.seen = []; studio.on('beamer', (e) => window.seen.push(`${e.scope} ${e.state}`));
        studio.on('chat', (e) => e.kind === 'turn-end' && window.seen.push('turn-end')); }""")
    catch_turn_end(page)
    send(page, "#scenario:beamer-live")  # an Edit of the .tex, then 4 s of work
    turn_end(page)
    seen = page.evaluate("() => window.seen")
    assert seen[0] == "full running" and seen.index("full running") < seen.index("turn-end"), seen
    compiled(page)
    assert page.evaluate("() => window.seen.filter((s) => s === 'full running').length") == 1  # none more at the end
    assert "Still compiles, live." in (studio.kit / START).read_text(encoding="utf-8")


def test_a_compile_that_ends_while_the_deck_opens_still_reaches_the_view(studio, page, api):
    # the start mode opens the deck while the studio compiles it: the compile may end after the server answered the
    # open (compiling) and before the page read that answer
    def idle():
        return [p for p in beamer_projects(studio, api) if p["last"] and not p["running"]]

    wait_until(idle, 90, "the compiles before")
    (studio.kit / START).write_text(BROKEN.replace(r"\nosuchmacro", "Raced."), encoding="utf-8")  # compiles on open
    held = []  # the page's open request, with the server's answer to it
    page.route("**/api/beamer/projects/*/open", lambda route: held.append((route, route.fetch())))
    open_studio(page, studio)
    wait_until(lambda: held or page.wait_for_timeout(100), 30, "the open request")
    route, answer = held[0]
    assert answer.json()["running"] == "full"
    old = answer.json()["view"]["version"]
    wait_until(lambda: [p for p in idle() if p["view"]["version"] != old], 90, "the compile")
    page.wait_for_timeout(1000)  # its events reach the page before the answer does
    route.fulfill(response=answer)
    expect(page.locator(".beamer-bar [role=status]")).to_have_text(re.compile(r"^Compilado em \d+,\d s$"))
    expect(page_image(page)).to_have_accessible_name("Página 1 de 3")
