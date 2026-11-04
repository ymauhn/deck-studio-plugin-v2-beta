"""latexmk needs Perl (bug of 2026-11-04: "could not find the script engine 'perl'", citations as [?]). The engine
finds a perl (PATH, Git for Windows, Strawberry) and gives it to the TeX tools only; with none it compiles with the
engine, bibtex or biber, and the engine twice. Real LaTeX on a fixture deck and on copies of the kit's v2 decks."""
import os
import shutil
import tempfile
from pathlib import Path

import pymupdf
import pytest

from deck_studio.beamer import engine
from tests.helpers.kit_copy import REAL_KIT

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "beamer-bib"
V2 = [("v2-colegas", "nexus-go-v2.tex"), ("v2-colegas-pt", "nexus-go-v2-pt.tex")]


def text_of(pdf):
    with pymupdf.open(pdf) as d:
        return "\n".join(page.get_text() for page in d)


@pytest.fixture
def tmp():
    with tempfile.TemporaryDirectory(prefix="deck-studio-perl-") as d:
        yield Path(d)


def test_perl_is_found_on_path_first_then_in_the_usual_folders(tmp):
    on_path, git = tmp / "on path", tmp / "Git" / "usr" / "bin"
    for folder in (on_path, git):
        folder.mkdir(parents=True)
        (folder / "perl.exe").write_bytes(b"")
    assert engine.find_perl(path=str(on_path), places=[str(git)]) == str(on_path)
    assert engine.find_perl(path="", places=[str(tmp / "none"), str(git)]) == str(git)
    assert engine.find_perl(path="", places=[str(tmp / "none"), "%NO_SUCH_VARIABLE%\\perl"]) is None


def test_perl_reaches_only_the_tex_tools_at_the_end_of_their_path():
    before = os.environ["PATH"]
    env = engine.tex_env("C:\\Perl Folder\\bin")
    assert env["PATH"] == before + os.pathsep + "C:\\Perl Folder\\bin"
    assert env["MIKTEX_CORE_ALLOWUNSAFEINPUTFILES"] == "false"
    assert os.environ["PATH"] == before
    assert engine.tex_env(None)["PATH"] == before


@pytest.mark.parametrize("perl", ["found", None])
def test_a_deck_with_a_bibliography_compiles_with_its_citations_with_or_without_perl(tmp, perl):
    if perl == "found":
        perl = engine.find_perl()
        if not perl:
            pytest.skip("no perl on this machine")
    project = tmp / "deck"
    shutil.copytree(FIXTURE, project)
    result = engine.compile({"kind": "handwritten", "main": str(project / "cite.tex")}, tmp / "work", perl=perl)
    assert result["ok"], result["errors"]
    text = text_of(result["pdf"])
    assert "[?]" not in text
    assert "[1]" in text and "[2]" in text
    assert "Kipf" in text  # the reference list


def test_without_perl_a_failed_compile_says_first_what_to_install(tmp):
    project = tmp / "deck"
    shutil.copytree(FIXTURE, project)
    main = project / "cite.tex"
    main.write_text(main.read_text(encoding="utf-8").replace("\\end{frame}", "\\undefinedcommand\\end{frame}", 1),
                    encoding="utf-8")
    result = engine.compile({"kind": "handwritten", "main": str(main)}, tmp / "work", perl=None)
    assert not result["ok"]
    assert result["errors"][0]["message"] == engine.NO_PERL
    assert "Git for Windows" in engine.NO_PERL and "Strawberry" in engine.NO_PERL
    assert any(e["line"] for e in result["errors"][1:])  # the TeX error still points at its line


@pytest.mark.parametrize("folder,name", V2)
@pytest.mark.parametrize("perl", ["found", None])
def test_the_kits_v2_decks_compile_without_any_unresolved_citation(tmp, folder, name, perl):
    """On a copy of the folder: the kit's .tex files are never written."""
    source = REAL_KIT / "beamer" / folder
    if not (source / name).is_file():
        pytest.skip(f"the kit has no beamer/{folder}/{name}")
    if perl == "found":
        perl = engine.find_perl()
        if not perl:
            pytest.skip("no perl on this machine")
    project = tmp / folder
    # its figures (logo PDFs) come along; the old run's outputs stay behind
    shutil.copytree(source, project, ignore=shutil.ignore_patterns("*.aux", "*.log", "*.bbl", "*.blg", "*.synctex.gz",
                                                                   "*.fdb_latexmk", "*.fls"))
    result = engine.compile({"kind": "handwritten", "main": str(project / name)}, tmp / "work", perl=perl)
    assert result["ok"], result["errors"][:3]
    assert "[?]" not in text_of(result["pdf"])
