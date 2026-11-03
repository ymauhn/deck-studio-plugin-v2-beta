import shutil
import tempfile
from pathlib import Path

import pytest

from deck_studio.core.history import Turn, UndoResult, create_history
from deck_studio.core.source_edit import replace_text


@pytest.fixture
def setup():
    """A throwaway kit and history folder under the OS temp dir, removed after the test."""
    tmp = Path(tempfile.mkdtemp(prefix="deck-studio-history-"))
    kit = tmp / "kit"
    (kit / "deck" / "src" / "slides").mkdir(parents=True)
    yield kit, tmp / "history", kit / "deck" / "src" / "slides" / "03-data.html"
    shutil.rmtree(tmp, ignore_errors=True)


# exact bytes, with no newline translation
def put(p, text):
    p.write_bytes(text.encode())


def got(p):
    return p.read_bytes().decode()


def test_undo_restores_the_exact_bytes_a_file_had_before_the_turn(setup):
    kit, dir, slide = setup
    # BOM, CRLF and LF lines, and bytes that are not valid UTF-8
    before = b"\xef\xbb\xbf" + b"<li>a</li>\r\n<li>b</li>\n" + b"\xff\x00"
    slide.write_bytes(before)
    h = create_history(dir, kit)
    h.begin("t1", {"kind": "agent"})
    h.before_write("t1", slide)
    slide.write_bytes(b"<li>changed</li>\n")
    h.end("t1")
    r = h.undo("t1")
    assert r == UndoResult(ok=True, restored=["deck/src/slides/03-data.html"], removed=[])
    assert slide.read_bytes() == before


def test_a_file_is_snapshotted_only_at_its_first_write_in_a_turn_whatever_the_path_spelling(setup):
    kit, dir, slide = setup
    put(slide, "v1\n")
    h = create_history(dir, kit)
    h.begin("t1", {})
    h.before_write("t1", slide)
    put(slide, "v2\n")
    h.before_write("t1", str(slide).upper().replace("\\", "/"))
    put(slide, "v3\n")
    h.end("t1")
    assert h.undo("t1") == UndoResult(ok=True, restored=["deck/src/slides/03-data.html"], removed=[])
    assert got(slide) == "v1\n"


def test_a_relative_path_is_taken_from_the_kit_root_not_from_the_working_directory(setup):
    kit, dir, slide = setup
    put(slide, "v1\n")
    h = create_history(dir, kit)
    h.begin("t1", {})
    h.before_write("t1", "deck/src/slides/03-data.html")
    put(slide, "v2\n")
    h.end("t1")
    assert h.undo("t1") == UndoResult(ok=True, restored=["deck/src/slides/03-data.html"], removed=[])
    assert got(slide) == "v1\n"


def test_undo_removes_a_file_the_turn_created(setup):
    kit, dir, slide = setup
    created = kit / "context" / "notes.md"
    h = create_history(dir, kit)
    h.begin("t1", {})
    h.before_write("t1", created)
    created.parent.mkdir(parents=True)
    put(created, "# notes\n")
    h.end("t1")
    assert h.undo("t1") == UndoResult(ok=True, restored=[], removed=["context/notes.md"])
    assert not created.exists()


def test_undo_leaves_alone_the_files_a_turn_snapshotted_but_did_not_change(setup):
    kit, dir, slide = setup
    put(slide, "v1\n")
    h = create_history(dir, kit)
    h.begin("t1", {})
    h.before_write("t1", slide)
    h.before_write("t1", kit / "context" / "never-written.md")
    h.end("t1")
    assert h.undo("t1") == UndoResult(ok=True, restored=[], removed=[])
    assert h.diff("t1") == ""


def test_undo_refuses_with_a_conflict_and_changes_nothing_when_a_file_changed_after_the_turn(setup):
    kit, dir, slide = setup
    other = kit / "deck" / "src" / "slides" / "04-method.html"
    put(slide, "a1\n")
    put(other, "b1\n")
    h = create_history(dir, kit)
    h.begin("t1", {})
    h.before_write("t1", slide)
    h.before_write("t1", other)
    put(slide, "a2\n")
    put(other, "b2\n")
    h.end("t1")
    put(other, "b3, typed later\n")
    assert h.undo("t1") == UndoResult(ok=False, conflicts=["deck/src/slides/04-method.html"])
    assert got(slide) == "a2\n"
    assert got(other) == "b3, typed later\n"


def turn(h, turn_id, file, text):
    """One turn that rewrites a file."""
    h.begin(turn_id, {})
    h.before_write(turn_id, file)
    file.parent.mkdir(parents=True, exist_ok=True)
    put(file, text)
    h.end(turn_id)


def test_two_turns_on_one_file_undo_newest_first_and_the_older_one_conflicts_until_then(setup):
    kit, dir, slide = setup
    put(slide, "v1\n")
    h = create_history(dir, kit)
    turn(h, "t1", slide, "v2\n")
    turn(h, "t2", slide, "v3\n")
    assert h.undo("t1") == UndoResult(ok=False, conflicts=["deck/src/slides/03-data.html"])
    assert h.undo("t2").ok is True
    assert got(slide) == "v2\n"
    assert h.undo("t1").ok is True
    assert got(slide) == "v1\n"


def test_turns_persist_in_the_history_folder_so_a_new_instance_can_undo_them(setup):
    kit, dir, slide = setup
    put(slide, "v1\n")
    turn(create_history(dir, kit), "t1", slide, "v2\n")
    later = create_history(dir, kit)
    assert later.undo("t1") == UndoResult(ok=True, restored=["deck/src/slides/03-data.html"], removed=[])
    assert got(slide) == "v1\n"


def test_diff_is_one_unified_diff_of_the_turn_with_kit_relative_paths_and_the_changed_lines(setup):
    kit, dir, slide = setup
    put(slide, "<ul>\r\n  <li>Labels per protein (mean)</li>\r\n  <li>Label matrix density</li>\r\n</ul>\r\n")
    notes = kit / "context" / "notes.md"
    h = create_history(dir, kit)
    h.begin("t1", {})
    h.before_write("t1", slide)
    put(slide, "<ul>\r\n  <li>Mean labels per protein</li>\r\n  <li>Label matrix density</li>\r\n</ul>\r\n")
    h.before_write("t1", notes)
    notes.parent.mkdir()
    put(notes, "# Notes\n")
    h.end("t1")
    d = h.diff("t1")
    for line in [
        "--- a/deck/src/slides/03-data.html",
        "+++ b/deck/src/slides/03-data.html",
        "-  <li>Labels per protein (mean)</li>",
        "+  <li>Mean labels per protein</li>",
        "--- /dev/null",
        "+++ b/context/notes.md",
        "+# Notes",
    ]:
        assert line in d, f"missing {line!r} in\n{d}"
    assert str(kit) not in d, "the diff names files by kit-relative paths"


def test_get_and_list_describe_the_turns_oldest_first_also_from_a_new_instance(setup):
    kit, dir, slide = setup
    put(slide, "v1\n")
    h = create_history(dir, kit)
    h.begin("turn-b", {"chatId": "c1", "kind": "agent"})
    h.before_write("turn-b", slide)
    put(slide, "v2\n")
    assert h.get("turn-b") == Turn(id="turn-b", meta={"chatId": "c1", "kind": "agent"}, files=["deck/src/slides/03-data.html"], ended=False, undone=False)
    h.end("turn-b")
    turn(h, "turn-a", slide, "v3\n")
    h.undo("turn-a")
    later = create_history(dir, kit)
    assert [[x.id, x.ended, x.undone] for x in later.list()] == [["turn-b", True, False], ["turn-a", True, True]]
    assert later.get("missing") is None


def test_an_in_place_text_edit_is_a_turn_of_its_own_with_a_diff_and_an_undo(setup):
    kit, dir, slide = setup
    src = '<ul class="b">\r\n    <li class="f" data-f="3">Labels per protein (mean): 25.91 BP</li>\r\n</ul>\r\n'
    put(slide, src)
    h = create_history(dir, kit)
    edit = replace_text(src, line=2, col=5, child_index=0, old_text="Labels per protein (mean): 25.91 BP", new_text="Mean labels per protein: 25.91 BP")
    h.begin("edit-1", {"kind": "edit"})
    h.before_write("edit-1", slide)
    put(slide, edit.html)
    h.end("edit-1")
    assert '+    <li class="f" data-f="3">Mean labels per protein: 25.91 BP</li>' in h.diff("edit-1")
    assert h.undo("edit-1").ok is True
    assert got(slide) == src


def test_a_damaged_turn_record_does_not_stop_the_history_from_loading_the_others(setup):
    kit, dir, slide = setup
    put(slide, "v1\n")
    turn(create_history(dir, kit), "t1", slide, "v2\n")
    put(dir / "t2.json", '{"id":"t2","seq":2,"files":[{"pa')
    assert [x.id for x in create_history(dir, kit).list()] == ["t1"]


def test_diff_names_a_changed_binary_file_in_one_line_instead_of_printing_its_bytes(setup):
    kit, dir, slide = setup
    img = kit / "deck" / "src" / "img" / "fig_ctx.png"
    h = create_history(dir, kit)
    h.begin("t1", {})
    h.before_write("t1", img)
    img.parent.mkdir(parents=True)
    img.write_bytes(bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0, 0, 0, 13, 0x49, 0x48, 0x44, 0x52]))
    h.end("t1")
    assert h.diff("t1") == "Binary files /dev/null and b/deck/src/img/fig_ctx.png differ\n"


def test_a_file_on_another_drive_is_named_by_its_absolute_path(setup):
    kit, dir, slide = setup
    drive = "Y:" if str(kit).upper().startswith("Z:") else "Z:"
    h = create_history(dir, kit)
    h.begin("t1", {})
    h.before_write("t1", f"{drive}\\skills\\deck-rules\\SKILL.md")
    assert h.get("t1").files == [f"{drive}/skills/deck-rules/SKILL.md"]
