"""The Autônomo level's shell rule (feedback of 2026-11-04: the deck's own build and QA, and plain reads, still asked).
The commands below are the ones the agent ran in the author's session of that day, with the kit path as Git Bash
writes it (/c/Users/...)."""
import sys

import pytest

# Windows paths (C:\Users\...) as the kit root: the guard's Windows semantics, tested on Windows; Linux has
# tests/unit/test_plataforma.py::test_the_write_guard_on_posix_paths
pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows paths")

import pytest

from deck_studio.config import nexus_go_config
from deck_studio.core.shell_policy import local_command
from deck_studio.core.write_guard import create_guard

KIT = "C:\\Users\\Yeonatan\\OneDrive\\Desktop\\nexusgo_deck_kit"
BASH_KIT = "/c/Users/Yeonatan/OneDrive/Desktop/nexusgo_deck_kit"
SCRIPTS = nexus_go_config(KIT)["localScripts"]
guard = create_guard({**nexus_go_config(KIT), "kitRoot": KIT})


def ok(command):
    return local_command(command, KIT, SCRIPTS)[0]


@pytest.mark.parametrize("command", [
    f'cd "{BASH_KIT}" && node deck/build.mjs --pt 2>&1 | tail -5',
    f'cd "{BASH_KIT}" && node deck/build.mjs 2>&1 | tail -2 && node deck/build.mjs --pt 2>&1 | tail -2 && (python qa/run_all.py 2>&1 | tail -40)',
    f'cd "{BASH_KIT}" && (NX_PT=1 python qa/run_all.py 2>&1 | grep -v "storyline says" | tail -25)',
    "python -I -u deck/tools/export_pdf.py",
    "python -I qa/audit_numbers.py",
    f'cd "{BASH_KIT}/deck" && diff -rq src src-pt | grep -v "^Only" ; diff src/engine.js src-pt/engine.js && echo ENGINE_SAME',
    f'cd "{BASH_KIT}/deck/src/slides" && grep -n \'data-f=\\|<section\\|data-component\' 00-opening.html 07-backup.html',
    f'cd "{BASH_KIT}/source/thesis" && sed -n \'185,190p\' dissertation.tex | grep -oiE "million|UniProt"',
    'cat "C:/Users/Yeonatan/Documents/notas da banca.md"',  # reading outside the kit, read only
    "Get-ChildItem deck/src-pt/slides | Select-Object Name",
    "git status --short && git diff --stat",
    'cd beamer/v2-colegas && latexmk -norc -pdf -interaction=nonstopmode nexus-go-v2.tex',
    "pdflatex -interaction=nonstopmode talk.tex >/dev/null && bibtex talk",
    'find deck/src -name "*.html" | wc -l',
])
def test_the_decks_own_commands_and_reads_pass(command):
    assert ok(command), local_command(command, KIT, SCRIPTS)
    assert guard.check("Bash", {"command": command}, "auto").behavior == "allow"


@pytest.mark.parametrize("command,why", [
    ("powershell -NoProfile -File deck/tools/publish_netlify.ps1", "externa"),
    ("npx netlify deploy --prod", "externa"),
    ("git push origin main", "externa"),
    ("curl https://example.org -o x", "externa"),
    ("Invoke-WebRequest https://x.org", "externa"),
    (f'cd "{BASH_KIT}/deck/src/slides" && python - <<\'EOF\'\nprint(1)\nEOF', "heredoc"),
    ('python -I /c/Users/Yeonatan/AppData/Local/Temp/ptcheck/s42.py "$(pwd)"', "substituição"),
    ("python -c \"open('deck/src/engine.js','w')\"", "python -c"),
    ("python -m http.server", "python -m"),
    ("python C:/Users/Yeonatan/AppData/Local/Temp/x.py", "não é do deck"),
    ("cd /c/Users/Yeonatan/AppData/Local/Temp && python qa/run_all.py", "não é do deck"),
    ("echo x > deck/src/slides/00-opening.html", "redirecionamento"),
    ("cat notas.md >> DECISIONS.md", "redirecionamento"),
    ("cp src/components/int-fold.js src-pt/components/int-fold.js", "cp"),
    ("rm -rf deck/src", "rm"),
    ("mkdir -p /c/Users/Yeonatan/AppData/Local/Temp/ptcheck", "mkdir"),
    ("sed -i 's/a/b/' deck/src/slides/00-opening.html", "sed que grava"),
    ("find . -name '*.tmp' -delete", "find"),
    ("latexmk -pdf talk.tex", "latexmk sem -norc"),
    ("pdflatex -shell-escape talk.tex", "shell escape"),
    ("npm run build", "npm"),
    ("for d in src src-pt; do ls $d; done", "for"),
])
def test_writes_external_actions_and_unknown_commands_still_ask(command, why):
    passed, reason = local_command(command, KIT, SCRIPTS)
    assert not passed, command
    assert why.lower() in reason.lower() or why in command, reason
    assert guard.check("Bash", {"command": command}, "auto").behavior == "ask"


def test_the_web_asks_at_every_level_and_reading_outside_passes_only_in_auto():
    for level in ("ask", "deck", "auto"):
        assert guard.check("WebFetch", {"url": "https://example.org"}, level).behavior == "ask", level
        assert guard.check("WebSearch", {"query": "x"}, level).behavior == "ask", level
    assert guard.check("Read", {"file_path": "C:\\Users\\Yeonatan\\Documents\\notas.md"}, "auto").behavior == "allow"
    assert guard.check("Read", {"file_path": "C:\\Users\\Yeonatan\\Documents\\notas.md"}, "deck").behavior == "ask"


def test_every_local_script_is_protected_so_it_is_never_changed_and_run_without_the_author():
    for rel in SCRIPTS:
        path = f"{KIT}\\{rel}".replace("/", "\\")
        assert guard.check("Edit", {"file_path": path}, "auto").behavior == "ask", rel
