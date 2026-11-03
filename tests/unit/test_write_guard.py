from dataclasses import replace

from deck_studio.config import nexus_go_config
from deck_studio.core.write_guard import WRITE_TOOLS, create_guard

# a kit root with a space and an accent, and the NEXUS-GO write policy (contract item 6)
KIT = "C:\\Users\\Yeonatan\\OneDrive\\Área de Trabalho\\deck kit"
SKILLS = "C:\\Users\\Yeonatan\\.claude\\skills"
guard = create_guard({
    "kit_root": KIT,
    "allow_write": ["deck/src/**", "context/**", ".claude/skills/**"],
    "deny_write": ["source/**", "data/**", "beamer/slides.tex", "deck/dist/**", "deck/build/**"],
    "ask_write_dirs": [SKILLS],
    "read_dirs": [SKILLS],
})


def write(file_path):
    return guard.check("Write", {"file_path": file_path, "content": "x"})


def test_a_write_to_a_slide_source_is_allowed():
    r = write(f"{KIT}\\deck\\src\\slides\\03-data.html")
    assert r.behavior == "allow"
    assert r.paths == [f"{KIT}\\deck\\src\\slides\\03-data.html"]
    assert isinstance(r.reason, str)


def test_writes_to_data_and_source_are_denied_even_when_allow_write_also_covers_them():
    both = create_guard({"kit_root": KIT, "allow_write": ["data/**", "source/**"], "deny_write": ["source/**", "data/**"]})
    for f in ["data\\thesis_tables.json", "source\\thesis\\dissertation.tex"]:
        r = both.check("Write", {"file_path": f"{KIT}\\{f}", "content": "x"})
        assert r.behavior == "deny", f
        assert isinstance(r.reason, str)
        assert write(f"{KIT}\\{f}").behavior == "deny", f


def test_the_generated_beamer_slides_tex_is_denied_as_an_exact_file():
    assert write(f"{KIT}\\beamer\\slides.tex").behavior == "deny"


def test_a_kit_write_that_no_pattern_covers_asks_and_patterns_stop_at_segment_boundaries():
    for f in ["beamer\\notes.tex", "deck\\build.mjs", "deck\\srcx\\a.html", "README.md"]:
        r = write(f"{KIT}\\{f}")
        assert r.behavior == "ask", f
        assert r.paths == [f"{KIT}\\{f}"]


def test_a_write_outside_the_kit_is_denied():
    for f in ["C:\\Users\\Yeonatan\\Documents\\notes.txt", "D:\\deck kit\\deck\\src\\x.html", "C:\\Users\\Yeonatan\\.claude\\settings.json"]:
        r = write(f)
        assert r.behavior == "deny", f
        assert r.paths == [f]


def test_a_write_in_the_user_skills_folder_asks():
    r = write(f"{SKILLS}\\deck-rules\\SKILL.md")
    assert r.behavior == "ask"
    assert r.paths == [f"{SKILLS}\\deck-rules\\SKILL.md"]
    assert write(f"{SKILLS}-old\\deck-rules\\SKILL.md").behavior == "deny"


def test_backslash_forward_slash_mixed_case_and_long_path_forms_of_a_path_classify_alike():
    fwd = KIT.replace("\\", "/")
    for f in [
        f"{KIT}\\data\\thesis_tables.json",
        f"{fwd}/data/thesis_tables.json",
        f"{KIT.upper()}\\DATA\\Thesis_Tables.JSON",
        f"c:{KIT[2:]}/Data\\thesis_tables.json",
        f"\\\\?\\{KIT}\\data\\thesis_tables.json",
        f"//?/{fwd}/data/thesis_tables.json",
    ]:
        assert write(f).behavior == "deny", f
    slide = f"{KIT}\\deck\\src\\slides\\03-data.html"
    for f in [
        f"{fwd}/deck/src/slides/03-data.html",
        f"{KIT}/deck\\src/slides\\03-data.html",
        f"\\\\?\\{KIT}\\deck\\src\\slides\\03-data.html",
        f"//?/{fwd}/deck/src/slides/03-data.html",
    ]:
        assert write(f) == replace(write(slide), paths=[slide]), f
    assert write(f"{KIT.lower()}\\DECK\\SRC\\slides\\03-data.html").behavior == "allow"


def test_win32_name_trimming_and_device_paths_cannot_dodge_a_deny():
    # Win32 drops a trailing dot from a folder name (data.\x is data\x) and trailing dots and spaces from a file name
    assert write(f"{KIT}\\data.\\thesis_tables.json").behavior == "deny"
    assert write(f"{KIT}\\beamer\\slides.tex. ").behavior == "deny"
    # a device path is never taken for a path inside the kit
    for f in ["\\\\?\\GLOBALROOT\\Device\\HarddiskVolume3\\kit\\deck\\src\\x.html", "\\\\.\\pipe\\deck", "//./NUL"]:
        assert write(f).behavior == "deny", f


def test_dotdot_is_resolved_before_matching_so_it_cannot_climb_out_of_an_allowed_folder():
    cases = {
        f"{KIT}\\deck\\src\\..\\..\\data\\thesis_tables.json": "deny",
        "deck/src/slides/../../../source/thesis/dissertation.tex": "deny",
        f"{KIT}\\context\\..\\deck\\build\\studio\\nexus-go-defense.html": "deny",
        f"{KIT}\\deck\\src\\..\\..\\..\\outside.txt": "deny",
        f"{KIT}\\data\\..\\deck\\src\\slides\\03-data.html": "allow",
    }
    for f, behavior in cases.items():
        assert write(f).behavior == behavior, f
    assert write(f"{KIT}\\deck\\src\\..\\..\\data\\x.json").paths == [f"{KIT}\\data\\x.json"]


def test_a_sibling_folder_whose_name_starts_with_the_kit_name_is_outside_the_kit():
    g = create_guard({"kit_root": "C:/kit", "allow_write": ["deck/src/**"], "deny_write": []})
    assert g.check("Write", {"file_path": "C:/kit/deck/src/a.html"}).behavior == "allow"
    assert g.check("Write", {"file_path": "C:/kit2/deck/src/a.html"}).behavior == "deny"


def test_relative_paths_resolve_against_the_kit_root():
    r = write("deck/src/slides/03-data.html")
    assert r.behavior == "allow"
    assert r.paths == [f"{KIT}\\deck\\src\\slides\\03-data.html"]
    assert write("data\\thesis_tables.json").behavior == "deny"
    assert write("README.md").behavior == "ask"


def test_edit_multi_edit_and_notebook_edit_follow_the_write_policy():
    assert guard.check("Edit", {"file_path": f"{KIT}\\deck\\src\\slides\\03-data.html", "old_string": "a", "new_string": "b"}).behavior == "allow"
    assert guard.check("MultiEdit", {"file_path": f"{KIT}\\data\\thesis_tables.json", "edits": []}).behavior == "deny"
    nb = guard.check("NotebookEdit", {"notebook_path": f"{KIT}\\context\\analysis.ipynb", "new_source": "x"})
    assert nb.behavior == "allow"
    assert nb.paths == [f"{KIT}\\context\\analysis.ipynb"]
    assert guard.check("NotebookEdit", {"notebook_path": "C:\\elsewhere\\a.ipynb", "new_source": "x"}).behavior == "deny"


def test_read_glob_and_grep_are_allowed_inside_the_kit_and_the_read_folders_and_ask_elsewhere():
    def read(file_path):
        return guard.check("Read", {"file_path": file_path})
    r = read(f"{KIT}\\source\\thesis\\dissertation.tex")
    assert r.behavior == "allow"
    assert r.paths == [f"{KIT}\\source\\thesis\\dissertation.tex"]
    assert read(f"{SKILLS}\\tdd\\SKILL.md").behavior == "allow"
    assert read("C:\\Users\\Yeonatan\\.ssh\\id_ed25519").behavior == "ask"
    assert read(f"{KIT}\\..\\notes.txt").behavior == "ask"
    glob = guard.check("Glob", {"pattern": "**/*.html"})
    assert glob.behavior == "allow"
    assert glob.paths == [KIT]
    assert guard.check("Grep", {"pattern": "CAFA", "path": "deck/src"}).behavior == "allow"
    assert guard.check("Grep", {"pattern": "token", "path": "C:\\Users\\Yeonatan"}).behavior == "ask"
    assert guard.check("Glob", {"pattern": "*.md", "path": "C:/Users/Yeonatan/Documents"}).behavior == "ask"


def test_a_glob_pattern_that_reaches_outside_the_readable_folders_asks():
    # the Glob tool honors an absolute pattern even when path points elsewhere
    assert guard.check("Glob", {"pattern": "C:/Users/Yeonatan/.ssh/*"}).behavior == "ask"
    assert guard.check("Glob", {"pattern": "../**/*.env"}).behavior == "ask"
    assert guard.check("Glob", {"pattern": f"{KIT.replace('\\', '/')}/deck/src/**/*.html"}).behavior == "allow"
    assert guard.check("Glob", {"pattern": f"{SKILLS}\\*\\SKILL.md"}).behavior == "allow"


def test_shell_and_web_tools_ask():
    for tool, tool_input in [
        ("Bash", {"command": "node deck/build.mjs"}),
        ("PowerShell", {"command": "Get-ChildItem"}),
        ("WebFetch", {"url": "https://example.org", "prompt": "x"}),
        ("WebSearch", {"query": "CAFA5"}),
    ]:
        r = guard.check(tool, tool_input)
        assert r.behavior == "ask", tool
        assert r.paths == [], tool
        assert isinstance(r.reason, str)


def test_subagent_tools_are_denied_since_their_edits_would_escape_undo():
    for tool in ["Task", "Agent"]:
        r = guard.check(tool, {"description": "edit slides", "prompt": "x", "subagent_type": "general-purpose"})
        assert r.behavior == "deny", tool
        assert r.paths == []


def test_the_deck_mcp_tools_skill_todo_write_and_tool_search_are_allowed():
    for tool, tool_input in [
        ("mcp__deck__screenshot_slide", {"slide": 13}),
        ("mcp__deck__add_image", {"contextFile": "fig.png"}),
        ("Skill", {"skill": "deck-rules"}),
        ("TodoWrite", {"todos": []}),
        ("ToolSearch", {"query": "select:Read"}),
    ]:
        r = guard.check(tool, tool_input)
        assert r.behavior == "allow", tool
        assert r.paths == []


def test_a_write_or_read_without_a_usable_path_is_denied_instead_of_throwing():
    for tool, tool_input in [
        ("Write", {"content": "x"}),
        ("Edit", {"file_path": 42}),
        ("MultiEdit", {"file_path": ""}),
        ("NotebookEdit", {}),
        ("Read", {}),
        ("Write", None),
    ]:
        r = guard.check(tool, tool_input)
        assert r.behavior == "deny", f"{tool} {tool_input}"
        assert r.paths == []


def test_any_other_tool_asks():
    for tool in ["mcp__github__create_issue", "mcp__deck", "NewTool"]:
        r = guard.check(tool, {"file_path": f"{KIT}\\deck\\src\\slides\\03-data.html"})
        assert r.behavior == "ask", tool
        assert r.paths == []


def test_the_config_keys_may_also_be_spelled_as_in_the_node_adapter():
    g = create_guard({"kitRoot": KIT, "allowWrite": ["deck/src/**"], "denyWrite": ["data/**"], "askWriteDirs": [SKILLS], "readDirs": [SKILLS]})
    assert g.check("Write", {"file_path": "deck/src/slides/03-data.html"}).behavior == "allow"
    assert g.check("Write", {"file_path": "data/x.json"}).behavior == "deny"
    assert g.check("Write", {"file_path": f"{SKILLS}\\x\\SKILL.md"}).behavior == "ask"
    assert g.check("Read", {"file_path": f"{SKILLS}\\x\\SKILL.md"}).behavior == "allow"


def test_write_tools_name_the_input_key_that_holds_each_tools_path():
    assert WRITE_TOOLS == {"Write": "file_path", "Edit": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}


def test_write_path_is_the_normalized_file_a_write_tool_call_targets():
    assert guard.write_path("Edit", {"file_path": "deck/src/slides/03-data.html"}) == f"{KIT}\\deck\\src\\slides\\03-data.html"
    assert guard.write_path("NotebookEdit", {"notebook_path": f"//?/{KIT.replace('\\', '/')}/context/a.ipynb"}) == f"{KIT}\\context\\a.ipynb"
    assert guard.write_path("Read", {"file_path": "deck/src/slides/03-data.html"}) is None
    assert guard.write_path("Write", {"content": "x"}) is None


def test_the_adapter_denies_latexmk_rc_files_in_the_hand_written_beamer_folder():
    # latexmk runs a latexmkrc in its working folder as Perl; the studio passes -norc, the author's own runs do not
    g = create_guard(nexus_go_config(KIT))
    for name in ["latexmkrc", ".latexmkrc"]:
        assert g.check("Write", {"file_path": f"beamer/academico/{name}"}).behavior == "deny", name
    assert g.check("Write", {"file_path": "beamer/academico/nexus-go-academic.tex"}).behavior == "allow"


def test_the_adapter_asks_before_a_write_to_a_script_of_the_deck_or_its_shell():
    # the studio deck runs only the shell's own scripts, so the agent changes them with the author's approval
    g = create_guard(nexus_go_config(KIT))
    for rel in ["deck/src/engine.js", "deck/src/components/int-pipe.js", "deck/src/lib/chart.js", "deck/src/shell.html",
                "deck/src/components/new-helper.mjs"]:
        assert g.check("Write", {"file_path": rel}).behavior == "ask", rel
    for rel in ["deck/src/slides/03-data.html", "deck/src/deck.css", "deck/src/components/int-pipe.css",
                "deck/src/math.json", "deck/src/img/photo.png"]:
        assert g.check("Write", {"file_path": rel}).behavior == "allow", rel


def test_a_write_through_an_ntfs_stream_or_a_short_8_3_name_is_denied():
    # both name a file the rules would miss: engine.js::$DATA is engine.js, SHELL~1.HTM can be shell.html
    g = create_guard(nexus_go_config(KIT))
    for rel in ["deck/src/engine.js::$DATA", "beamer/slides.tex::$DATA", "deck/src/SHELL~1.HTM",
                "beamer/academico/LATEXM~1", "deck/src/slides/03-data.html:x"]:
        assert g.check("Write", {"file_path": rel}).behavior == "deny", rel
    assert g.check("Write", {"file_path": "deck/src/slides/03-data.html"}).behavior == "allow"
