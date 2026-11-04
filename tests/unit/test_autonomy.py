"""The autonomy levels of the chat switch, applied by the write guard (pedido 3, 2026-11-04).

"ask" (perguntar sempre), "deck" (editar o deck sem perguntar, the default) and "auto" (autônomo). At every level a
write outside the kit is denied or asks, the protected files stay denied, the deck's own scripts ask, and a shell
command that looks external (publish, network, git push) or reaches outside the kit asks."""
from deck_studio.config import nexus_go_config
from deck_studio.core.write_guard import LEVELS, create_guard

KIT = "C:\\Users\\Yeonatan\\OneDrive\\Área de Trabalho\\deck kit"
SKILLS = "C:\\Users\\Yeonatan\\.claude\\skills"
guard = create_guard({**nexus_go_config("."), "kitRoot": KIT, "askWriteDirs": [SKILLS], "readDirs": [SKILLS]})


def write(path, level):
    return guard.check("Write", {"file_path": f"{KIT}\\{path}", "content": "x"}, level).behavior


def shell(command, level, tool="Bash"):
    return guard.check(tool, {"command": command}, level).behavior


def test_the_levels_are_ask_deck_and_auto():
    assert LEVELS == ("ask", "deck", "auto")


def test_ask_always_asks_even_for_a_slide_edit():
    assert write("deck\\src\\slides\\03-data.html", "ask") == "ask"
    assert guard.check("Edit", {"file_path": f"{KIT}\\context\\notes.md"}, "ask").behavior == "ask"


def test_deck_edits_any_unprotected_kit_file_without_asking():
    assert write("deck\\src\\slides\\03-data.html", "deck") == "allow"
    assert write("README.md", "deck") == "allow"
    assert write("deck\\package.json", "deck") == "allow"


def test_deck_still_asks_for_shell_web_and_reads_outside_the_kit():
    assert shell("npm run lint", "deck") == "ask"
    assert guard.check("WebFetch", {"url": "https://example.org"}, "deck").behavior == "ask"
    assert guard.check("Read", {"file_path": "C:\\Users\\Yeonatan\\notes.txt"}, "deck").behavior == "ask"


def test_auto_runs_local_commands_reads_and_web_lookups_without_asking():
    assert shell("npm run lint", "auto") == "allow"
    assert shell("Get-ChildItem deck/src/slides", "auto", "PowerShell") == "allow"
    assert guard.check("WebSearch", {"query": "gene ontology"}, "auto").behavior == "allow"
    assert guard.check("Read", {"file_path": "C:\\Users\\Yeonatan\\notes.txt"}, "auto").behavior == "allow"


def test_auto_still_asks_for_external_actions_and_commands_that_reach_outside_the_kit():
    for command in ["powershell -File deck/tools/publish_netlify.ps1", "npx netlify deploy --prod", "git push",
                    "curl https://example.org", "Invoke-WebRequest https://x.org", "npm publish", "gh pr create",
                    "ssh vps", "Remove-Item C:\\Users\\Yeonatan\\Documents\\x", "type ..\\secrets.txt",
                    "cat ~/.ssh/id_ed25519", "echo x > $env:USERPROFILE\\x.txt", "copy a %APPDATA%\\b",
                    "node -e \"require('fs').writeFileSync('deck/src/engine.js','')\"", "echo > deck/src/shell.html"]:
        assert shell(command, "auto") == "ask", command
    assert shell(f"type \"{KIT}\\deck\\src\\slides\\03-data.html\"", "auto") == "allow"


def test_at_every_level_writes_outside_the_kit_and_protected_files_never_go_through():
    for level in LEVELS:
        assert guard.check("Write", {"file_path": "C:\\Users\\Yeonatan\\x.txt"}, level).behavior == "deny", level
        assert write("source\\thesis\\dissertation.tex", level) == "deny", level
        assert write("deck\\dist\\nexus-go-defense.html", level) == "deny", level
        assert write("deck\\src\\engine.js", level) == "ask", level
        assert write("deck\\src\\shell.html", level) == "ask", level
        assert guard.check("Write", {"file_path": f"{SKILLS}\\x\\SKILL.md"}, level).behavior == "ask", level
        assert guard.check("Agent", {"prompt": "x"}, level).behavior == "deny", level
        assert guard.check("SomeNewTool", {}, level).behavior == "ask", level


def test_an_unknown_level_is_the_default_deck_level():
    assert write("README.md", "whatever") == "allow"
    assert write("deck\\src\\slides\\03-data.html", "whatever") == "allow"
