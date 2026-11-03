"""Beamer engine (seam 5): real LaTeX on the fixture deck and on a copy of the kit's beamer/academico."""
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

import pymupdf
import pytest

from deck_studio.beamer import engine
from tests.helpers.kit_copy import REAL_KIT

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "beamer"
TALK = {"kind": "handwritten", "main": str(FIXTURE / "talk.tex")}


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture(scope="module")
def tmp():
    with tempfile.TemporaryDirectory(prefix="deck-studio-beamer-") as d:
        yield Path(d)


@pytest.fixture(scope="module")
def talk_pdf(tmp):
    """The fixture deck compiled once; the work dir name has a space, like the author's paths."""
    result = engine.compile(TALK, tmp / "work dir")
    assert result["ok"], result["errors"]
    return result["pdf"]


def producer(pdf):
    with pymupdf.open(pdf) as d:
        return d.metadata["producer"]


def test_discover_projects_sorts_handwritten_and_generated(tmp_path):
    write(tmp_path / "beamer/nexus-go-defense.tex", "\\documentclass[aspectratio=169,11pt]{beamer}\n\\begin{document}\n\\input{slides}\n\\end{document}\n")
    write(tmp_path / "beamer/slides.tex", "\\begin{frame}[plain]\n\\end{frame}\n")
    write(tmp_path / "beamer/build/layout.json", "{}")
    write(tmp_path / "beamer/academico/nexus-go-academic.tex", "% hand-written\n\\documentclass[aspectratio=169,10pt]{beamer}\n")
    write(tmp_path / "beamer/academico/tables.tex", "\\newcommand\\tab{}\n")
    write(tmp_path / "beamer/notes.tex", "\\documentclass{article}\n")

    projects = engine.discover_projects(tmp_path)

    assert {p["rel"]: p["kind"] for p in projects} == {
        "beamer/academico/nexus-go-academic.tex": "handwritten",
        "beamer/nexus-go-defense.tex": "generated",
    }
    gen = next(p for p in projects if p["kind"] == "generated")
    assert Path(gen["main"]) == tmp_path / "beamer/nexus-go-defense.tex"


def test_frames_lists_begin_and_end_lines():
    text = (FIXTURE / "talk.tex").read_text(encoding="utf-8")
    text += "% \\begin{frame}{Commented out}\n% \\end{frame}\n"

    assert engine.frames(text) == [
        {"start": 10, "end": 12},
        {"start": 14, "end": 20},
        {"start": 22, "end": 32},
        {"start": 34, "end": 38},
    ]


def test_compile_builds_the_whole_deck_with_pdflatex(tmp):
    result = engine.compile(TALK, tmp / "full")

    assert result["ok"] and result["errors"] == []
    assert result["engine"] == "pdflatex"
    assert Path(result["pdf"]) == tmp / "full" / "talk.pdf"
    assert engine.page_count(result["pdf"]) == 8
    assert "pdfTeX" in producer(result["pdf"])
    assert sorted(p.name for p in FIXTURE.iterdir()) == ["figures", "talk.tex"]


def variant(d, old, new):
    """A copy of the fixture deck in d with one text change."""
    write(d / "talk.tex", (FIXTURE / "talk.tex").read_text(encoding="utf-8").replace(old, new))
    (d / "figures").mkdir()
    (d / "figures" / "dot.png").write_bytes((FIXTURE / "figures" / "dot.png").read_bytes())
    return {"kind": "handwritten", "main": str(d / "talk.tex")}


@pytest.fixture(scope="module")
def broken(tmp):
    """An undefined macro in the second bullet of frame 2 (line 17)."""
    return variant(tmp / "broken deck", "their nets", "their \\nosuchmacro nets")


def test_compile_reports_errors_with_file_and_line(broken, tmp):
    result = engine.compile(broken, tmp / "broken-full")

    assert not result["ok"]
    # TeX reads a frame body whole, so it reports errors on the frame's \end{frame} line
    assert [(Path(e["file"]), e["line"], e["message"]) for e in result["errors"]] == [
        (Path(broken["main"]), 20, "Undefined control sequence.")]


def test_frame_compile_errors_point_at_the_main_file(broken, tmp):
    result = engine.compile(broken, tmp / "broken-frame with a long folder name so that TeX would wrap its log", frame=1)

    assert not result["ok"]
    assert [(Path(e["file"]), e["line"], e["message"]) for e in result["errors"]] == [
        (Path(broken["main"]), 20, "Undefined control sequence.")]


@pytest.mark.parametrize("where, old, new", [
    ("magic", "% Deck Studio", "% !TEX program = xelatex\n% Deck Studio"),
    ("preamble", "\\graphicspath", "\\usepackage{fontspec}\n\\graphicspath"),
])
def test_compile_picks_xelatex_from_the_magic_comment_or_the_preamble(tmp, where, old, new):
    project = variant(tmp / f"xe-{where}", old, new)

    result = engine.compile(project, tmp / f"xe-{where}-work")

    assert result["ok"], result["errors"]
    assert result["engine"] == "xelatex"
    assert "dvipdfmx" in producer(result["pdf"])


def text_of(pdf):
    with pymupdf.open(pdf) as d:
        return " ".join(p.get_text() for p in d)


def test_compile_one_frame_is_the_preamble_plus_that_frame(tmp):
    result = engine.compile(TALK, tmp / "frames", frame=1)

    assert result["ok"], result["errors"]
    assert engine.page_count(result["pdf"]) == 3
    text = text_of(result["pdf"])
    assert "Gulls circle the old pier" in text
    assert "Fixture" not in text and "Mountain" not in text


def test_compile_runs_no_code_from_the_project_folder(tmp):
    """The agent writes in a hand-written deck's folder with no approval, so a compile must not read a latexmkrc
    there (it is Perl) and TeX must not reach a shell (\\write18)."""
    d = tmp / "rc deck"
    project = variant(d, "Thanks for listening.", "Thanks for listening. Shell escape \\the\\pdfshellescape.")
    write(d / "latexmkrc", "open(my $f, '>', 'rc-was-read.txt'); close($f);\n")

    result = engine.compile(project, tmp / "rc-work")

    assert result["ok"], result["errors"]
    assert not (d / "rc-was-read.txt").exists()
    assert "Shell escape 0." in text_of(result["pdf"])   # 0 is off; MiKTeX's default is 2, restricted


def test_compile_never_runs_lualatex_whose_lua_code_writes_in_the_project_folder(tmp):
    project = variant(tmp / "lua deck", "% Deck Studio", "% !TEX program = lualatex\n% Deck Studio")

    result = engine.compile(project, tmp / "lua-work")

    assert result["ok"], result["errors"]
    assert result["engine"] == "pdflatex"
    assert "pdfTeX" in producer(result["pdf"])


@pytest.mark.parametrize("where", ["absolute", "parent"])
def test_compile_refuses_an_input_of_a_file_from_outside_the_decks_folder(tmp, where):
    """The agent writes the deck's .tex with no approval, maybe on an imported PDF's say: an \\input of another file
    of the computer (a key, a login) must not land on a page that the agent then sees and the author shares."""
    secret = tmp / "outside" / "secret.tex"
    write(secret, "SECRET-4242\n")
    path = secret.as_posix() if where == "absolute" else "../outside/secret.tex"
    project = variant(tmp / f"input-{where}", "Thanks for listening.", f"Thanks for listening. \\input{{{path}}}")

    result = engine.compile(project, tmp / "data" / "beamer" / f"input-{where}")  # as the studio's, in another tree

    assert not result["ok"]
    assert "secret.tex" in " ".join(e["message"] for e in result["errors"])  # the file it could not read
    assert result["pdf"] is None or "SECRET-4242" not in text_of(result["pdf"])


def test_render_page_gives_a_png_of_one_page(talk_pdf):
    png = engine.render_page(talk_pdf, 2, dpi=72)

    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    pix = pymupdf.Pixmap(png)
    assert abs(pix.width - 453.5) < 1 and abs(pix.height - 255.1) < 1   # 160 x 90 mm (aspectratio=169) at 72 dpi
    assert engine.render_page(talk_pdf, 2, dpi=72) != engine.render_page(talk_pdf, 1, dpi=72)


def point(pdf, pno, word, nth=0):
    """Center (pt, from the top left) of the nth occurrence of a word on a 1-based page."""
    with pymupdf.open(pdf) as d:
        hits = [w for w in d[pno - 1].get_text("words") if re.sub(r"^\W+|\W+$", "", w[4]) == word]
    x0, y0, x1, y1 = hits[nth][:4]
    return (x0 + x1) / 2, (y0 + y1) / 2


@pytest.mark.parametrize("pno, word, nth, line", [
    (1, "Fixture", 0, 5),     # title page: \title in the preamble
    (1, "Deck", 1, 6),        # "Deck Studio", not "Fixture Deck"
    (2, "Water", 0, 14),      # frame title
    (2, "water", 0, 16),      # same word in a bullet
    (4, "Fishermen", 0, 17),
    (4, "Gulls", 0, 18),
    (5, "summit", 0, 26),
    (6, "Thunder", 0, 27),
    (7, "Thanks", 0, 35),
    (8, "Questions", 0, 37),
])
def test_locate_lands_clicks_on_words_on_their_exact_lines(talk_pdf, pno, word, nth, line):
    hit = engine.locate(talk_pdf, pno, *point(talk_pdf, pno, word, nth))

    assert Path(hit["file"]) == FIXTURE / "talk.tex"
    assert (hit["line"], hit["method"]) == (line, "synctex+text")
    assert word in hit["text"]
    start, end = {1: (10, 12), 2: (14, 20), 4: (14, 20), 5: (22, 32), 6: (22, 32), 7: (34, 38), 8: (34, 38)}[pno]
    assert hit["frame"] == {"start": start, "end": end}


def test_locate_off_text_falls_back_to_the_frame(talk_pdf):
    hit = engine.locate(talk_pdf, 3, 440, 240)

    assert (hit["frame"], hit["method"], hit["text"]) == ({"start": 14, "end": 20}, "synctex", "")


def test_locate_on_a_frame_compile_points_at_the_main_file(tmp):
    pdf = engine.compile(TALK, tmp / "frames", frame=1)["pdf"]

    hit = engine.locate(pdf, 3, *point(pdf, 3, "Gulls"))

    assert Path(hit["file"]) == FIXTURE / "talk.tex"
    assert (hit["line"], hit["frame"], hit["method"]) == (18, {"start": 14, "end": 20}, "synctex+text")


@pytest.fixture(scope="session")
def academic_pdf():
    """A copy of the kit's hand-written deck (pdfLaTeX, 48 frames, 55 pages), compiled once per session."""
    with tempfile.TemporaryDirectory(prefix="deck-studio-academico-") as d:
        src = Path(d) / "academico"
        shutil.copytree(Path(os.environ.get("STUDIO_KIT") or REAL_KIT) / "beamer" / "academico", src)
        result = engine.compile({"kind": "handwritten", "main": str(src / "nexus-go-academic.tex")}, Path(d) / "work")
        assert result["ok"], result["errors"]
        yield result["pdf"], src / "nexus-go-academic.tex"


@pytest.mark.parametrize("pno, word, nth, line, frame_start", [
    (1, "Mauhnoom", 0, 47, 57),          # title page: \author in the preamble
    (2, "Roadmap", 0, 61, 61),
    (2, "Background", 0, 64, 61),
    (3, "Millions", 0, 79, 79),
    (6, "Sequencing", 0, 82, 79),
    (6, "Automated", 0, 84, 79),
    (7, "acyclic", 0, 94, 89),
    (7, "hierarchical", 0, 96, 89),
    (9, "reliability", 0, 112, 105),     # \item<2->
    (10, "retention", 0, 127, 121),
    (11, "Benchmark", 0, 140, 134),
    (14, "language", 0, 187, 187),
    (14, "frozen", 0, 192, 187),
    (21, "aggregated", 0, 247, 247),
    (21, "binding", 0, 250, 247),
    (22, "proteins", 0, 258, 258),       # the same word in the title ...
    (22, "proteins", 1, 261, 258),       # ... and in a bullet
    (24, "interpretability", 0, 291, 286),
    (27, "architecture", 0, 334, 330),
])
def test_locate_on_the_academic_deck_finds_titles_and_bullets(academic_pdf, pno, word, nth, line, frame_start):
    pdf, main = academic_pdf

    hit = engine.locate(pdf, pno, *point(pdf, pno, word, nth))

    assert Path(hit["file"]) == main
    assert (hit["line"], hit["frame"]["start"], hit["method"]) == (line, frame_start, "synctex+text")


@pytest.fixture(scope="module")
def generated_kit(tmp):
    """A kit-like folder with the generated deck's outputs (never compiled here): PDF, .nav, sources, layout.json."""
    kit = Path(os.environ.get("STUDIO_KIT") or REAL_KIT)
    root = tmp / "generated kit"
    for rel in ("beamer/nexus-go-defense.tex", "beamer/nexus-go-defense.pdf", "beamer/nexus-go-defense.nav",
                "beamer/slides.tex", "beamer/build/layout.json"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(kit / rel, root / rel)
    return root


def test_page_map_starts_with_the_title_slide(generated_kit):
    pages = engine.page_map(generated_kit)

    assert len(pages) == 321
    assert pages[0] == {"page": 1, "slide": "s01", "n": 1, "step": 0, "state": "0", "kind": "step"}


def test_page_map_gives_consecutive_steps_extra_states_and_explorer_pages(generated_kit):
    pages = engine.page_map(generated_kit)
    at = lambda p: (pages[p - 1]["slide"], pages[p - 1]["step"], pages[p - 1]["state"], pages[p - 1]["kind"])

    assert [at(p) for p in range(3, 8)] == [("s03", 0, "0", "step"), ("s03", 1, "1", "step"), ("s03", 2, "2", "step"),
                                           ("s03", 3, "3", "step"), ("s04", 0, "0", "step")]
    assert [at(p) for p in (85, 86)] == [("s21", 6, "6", "step"), ("s21", 6, "all", "state")]
    assert [at(p) for p in (101, 102, 103)] == [("s24", 4, "T0", "state"), ("s24", 4, "T6", "state"),
                                               ("s24", 4, "4", "animation")]
    assert at(196) == ("b1", 0, "0", "step")
    assert [at(p) for p in (204, 205, 303, 304, 321)] == [("s21", 6, None, "explorer"), ("s24", 4, None, "explorer"),
                                                         ("s24", 4, None, "explorer"), ("s38", 4, None, "explorer"),
                                                         ("s38", 4, None, "explorer")]


def test_pdf_to_html_puts_pdf_words_inside_their_html_boxes(generated_kit):
    pdf = generated_kit / "beamer/nexus-go-defense.pdf"
    layout = json.loads((generated_kit / "beamer/build/layout.json").read_text(encoding="utf-8"))
    s03 = next(s for s in layout["slides"] if s["id"] == "s03")
    leaf = next(d for d in s03["leaves"].values() if any(t["s"] == "Sequencing" for t in d.get("toks", [])))
    rect = {t["s"]: t["r"] for t in leaf["toks"]}

    for word in ("Sequencing", "characterization", "expensive"):   # first word, a second-line word, the last word
        p = engine.pdf_to_html(*point(pdf, 6, word))   # page 6: s03, last step
        r = rect[word]
        assert r["x"] <= p["x"] <= r["x"] + r["w"] and r["y"] <= p["y"] <= r["y"] + r["h"], (word, p, r)
