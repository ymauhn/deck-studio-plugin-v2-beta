"""The findings of the recorded end-to-end test (2026-11-04): reading the deck from the terminal passes at the default
level; the agent writes to the author in Portuguese; a text edit can go after an inline formula."""
from deck_studio.agent.prompt import appendix
from deck_studio.config import nexus_go_config
from deck_studio.core.source_edit import replace_text
from deck_studio.core.write_guard import create_guard
from deck_studio.templates import PROJECT

KIT = "C:\\Users\\Yeonatan\\deck-gerador-testes\\teste-ponta-a-ponta\\Seminario de metodos"
BASH_KIT = "/c/Users/Yeonatan/deck-gerador-testes/teste-ponta-a-ponta/Seminario de metodos"
guard = create_guard({**nexus_go_config(KIT), "kitRoot": KIT})


def shell(command, level="deck"):
    return guard.check("Bash", {"command": command}, level).behavior


def test_reading_the_deck_from_the_terminal_passes_at_the_default_level():
    # the command that held the recorded test's agent for 10 minutes
    assert shell(f'cd "{BASH_KIT}" && find context deck/src .claude/skills -type f | head -100 && cat studio.json') == "allow"
    assert shell("grep -rn \"velocidade\" deck/src/slides") == "allow"
    assert shell("ls -la context && wc -l deck/src/slides/*.html") == "allow"


def test_at_the_default_level_reads_outside_the_deck_writes_and_code_still_ask():
    assert shell("cat C:/Users/Yeonatan/Documents/notas.md") == "ask"
    assert shell("cd /c/Users/Yeonatan && ls") == "ask"
    assert shell("cat ../segredo.txt") == "ask"
    assert shell("node deck/build.mjs") == "ask"  # runs code: only at Autônomo
    assert shell("node deck/build.mjs", "auto") == "allow"
    assert shell("echo x > deck/src/slides/00-title.html") == "ask"
    assert shell("curl https://example.org") == "ask"
    assert shell("ls", "ask") == "ask"  # perguntar sempre asks for everything


def test_every_message_to_the_author_is_in_portuguese():
    text = appendix(nexus_go_config(KIT))
    assert "Write every message to the author in Brazilian Portuguese" in text
    assert "short notes between tool calls" in text
    claude = (PROJECT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Every message to the author is in Brazilian Portuguese" in claude


def test_a_text_edit_can_go_after_an_inline_formula():
    html = "<ul>\n<li>Só se mede <i>M</i><sub>p</sub> sin <i>i</i></li>\n</ul>\n"
    r = replace_text(html, 2, 1, 5, "", " (editado à mão)")
    assert r.ok and r.html == "<ul>\n<li>Só se mede <i>M</i><sub>p</sub> sin <i>i</i> (editado à mão)</li>\n</ul>\n"
    assert not replace_text(html, 2, 1, 5, "x", "y").ok  # past the last child, only a new text goes
    assert not replace_text(html, 2, 1, 5, "", "  ").ok
    assert replace_text(html, 2, 1, 5, "", "<b>&").html.count("&lt;b&gt;&amp;") == 1  # escaped like any edit
