"""The write rules of a project made by Deck Studio (generic_config, docs/IMPORT.md "Config"), through the guard."""
import sys

import pytest

# Windows paths (C:\Users\...) as the kit root: the guard's Windows semantics, tested on Windows; Linux has
# tests/unit/test_plataforma.py::test_the_write_guard_on_posix_paths
pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows paths")

from pathlib import Path

from deck_studio.config import generic_config
from deck_studio.core.write_guard import create_guard

# a project folder with a space and an accent
KIT = "C:\\Users\\Yeonatan\\Deck Studio\\Relatório anual"
guard = create_guard(generic_config(KIT))


def write(rel):
    return guard.check("Write", {"file_path": rel, "content": "x"}).behavior


def test_the_project_config_and_the_build_outputs_are_denied():
    for rel in ["studio.json", "deck/build/studio/deck.html", "deck/build/studio/csp.json", "deck/dist/deck.html",
                "deck/dist/deck.pdf", "exports/relatorio-anual-overleaf.zip", f"{KIT}\\STUDIO.JSON"]:
        assert write(rel) == "deny", rel


def test_a_latexmk_rc_file_anywhere_under_beamer_is_denied():
    # latexmk runs a latexmkrc in its working folder as Perl; the studio passes -norc, Overleaf and the author do not
    for rel in ["beamer/apresentacao/latexmkrc", "beamer/apresentacao/.latexmkrc", "beamer/latexmkrc",
                "beamer/outra/sub/.latexmkrc"]:
        assert write(rel) == "deny", rel


def test_the_decks_code_its_build_the_tools_and_the_project_rules_ask():
    # the studio deck runs the shell's scripts, and the studio runs the build and the job tools
    for rel in ["deck/src/engine.js", "deck/src/lib/chart.js", "deck/src/x.mjs", "deck/src/x.cjs", "deck/src/shell.html",
                "deck/build.py", "deck/tools/export_pdf.py", "tools/overleaf_zip.py", "CLAUDE.md"]:
        assert write(rel) == "ask", rel


def test_a_claude_md_or_a_claude_folder_in_any_folder_asks_like_the_projects_own():
    # Claude Code reads a folder's CLAUDE.md as instructions when it works there: one written with no approval card
    # would steer the agent's later turns. So could a .claude folder (settings, rules) below the project's own
    for rel in ["deck/src/CLAUDE.md", "deck/src/slides/CLAUDE.md", "context/CLAUDE.md", "context/relatorio/claude.md",
                "beamer/CLAUDE.md", "beamer/apresentacao/CLAUDE.md", ".claude/skills/criar-apresentacao/CLAUDE.md",
                "context/.claude/settings.json", "deck/src/.claude/rules/estilo.md", "beamer/.claude/skills/x/SKILL.md"]:
        assert write(rel) == "ask", rel


def test_slides_styles_images_the_context_the_project_skills_and_the_beamer_sources_are_allowed():
    for rel in ["deck/src/slides/00-title.html", "deck/src/deck.css", "deck/src/img/p001-1.png",
                "context/relatorio-anual/texto.md", "context/relatorio.pdf", ".claude/skills/criar-apresentacao/SKILL.md",
                "beamer/apresentacao/apresentacao.tex", "beamer/apresentacao/figures/p001-1.png"]:
        assert write(rel) == "allow", rel


def test_the_user_skills_can_be_read_and_written_with_approval_as_in_the_nexus_go_config():
    skill = str(Path.home() / ".claude" / "skills" / "humanizer" / "SKILL.md")
    assert write(skill) == "ask"
    assert guard.check("Read", {"file_path": skill}).behavior == "allow"
    assert write(str(Path.home() / "Documents" / "notes.txt")) == "deny"
