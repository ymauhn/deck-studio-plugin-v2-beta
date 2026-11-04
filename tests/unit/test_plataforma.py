"""deck_studio.core.plataforma on the system it runs on (CI: Windows and Ubuntu): a byte lock held by another process
blocks a second lock and is seen by byte_locked without being taken; kill_tree stops a child and its own child."""
import os
import subprocess
import sys
import time

from deck_studio.core import plataforma

HOLD = """
import os, sys, time
from deck_studio.core import plataforma
fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT | plataforma.O_BINARY)
os.lseek(fd, 1 << 30, os.SEEK_SET)
plataforma.lock_byte(fd)
print("locked", flush=True)
time.sleep(60)
"""
TREE = """
import subprocess, sys, time
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
print(child.pid, flush=True)
time.sleep(60)
"""


def alive(pid):
    if plataforma.WINDOWS:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:  # a zombie (ended, not yet reaped by its parent) is not running
        with open(f"/proc/{pid}/stat") as f:
            return f.read().split(") ")[1][0] != "Z"
    except OSError:
        return False


def test_a_byte_another_process_locks_is_seen_and_cannot_be_locked_again(tmp_path):
    file = tmp_path / "studio.lock"
    holder = subprocess.Popen([sys.executable, "-c", HOLD, str(file)], stdout=subprocess.PIPE, text=True,
                              **plataforma.NEW_GROUP)
    try:
        assert holder.stdout.readline().strip() == "locked"
        fd = os.open(file, os.O_RDONLY | plataforma.O_BINARY)
        os.lseek(fd, 1 << 30, os.SEEK_SET)
        assert plataforma.byte_locked(fd)
        os.close(fd)
        fd = os.open(file, os.O_RDWR | plataforma.O_BINARY)
        os.lseek(fd, 1 << 30, os.SEEK_SET)
        try:
            plataforma.lock_byte(fd)
            raise AssertionError("locked a byte another process holds")
        except OSError:
            pass
        finally:
            os.close(fd)
    finally:
        plataforma.kill_tree(holder.pid)
        holder.wait(10)
    # the OS dropped the lock with the process: it is free now
    fd = os.open(file, os.O_RDWR | plataforma.O_BINARY)
    os.lseek(fd, 1 << 30, os.SEEK_SET)
    assert not plataforma.byte_locked(fd)
    plataforma.lock_byte(fd)
    plataforma.unlock_byte(fd)
    os.close(fd)


def test_kill_tree_stops_the_child_and_the_child_it_started():
    parent = subprocess.Popen([sys.executable, "-c", TREE], stdout=subprocess.PIPE, text=True,
                              creationflags=plataforma.NO_WINDOW, **plataforma.NEW_GROUP)
    grandchild = int(parent.stdout.readline())
    assert alive(grandchild)
    plataforma.kill_tree(parent.pid)
    parent.wait(10)
    end = time.monotonic() + 10
    while alive(grandchild) and time.monotonic() < end:
        time.sleep(0.1)
    assert not alive(grandchild)


def test_the_data_home_follows_the_system(monkeypatch, tmp_path):
    if plataforma.WINDOWS:
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        assert plataforma.data_home() == tmp_path / "deck-studio"
    else:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        assert plataforma.data_home() == tmp_path / "deck-studio"
        monkeypatch.delenv("XDG_DATA_HOME")
        assert plataforma.data_home().parts[-3:] == (".local", "share", "deck-studio")


def test_the_write_guard_reads_a_windows_short_name_as_its_long_folder(tmp_path):
    """The CI's %TEMP% comes as C:\\Users\\RUNNER~1\\...: a project there is still the project."""
    import ctypes

    import pytest

    from deck_studio.core.write_guard import create_guard
    if not plataforma.WINDOWS:
        pytest.skip("Windows short names")
    kit = tmp_path / "Um projeto com nome longo"
    (kit / "qa").mkdir(parents=True)
    buf = ctypes.create_unicode_buffer(1024)
    ctypes.windll.kernel32.GetShortPathNameW(str(kit), buf, 1024)
    if "~" not in buf.value:
        pytest.skip("no short names on this volume")
    guard = create_guard({"kitRoot": str(kit.resolve()), "allowWrite": ["deck/**"], "askWrite": ["qa/*.py"]})
    assert guard.check("Edit", {"file_path": buf.value + "\\qa\\check_deck.py"}, "deck").behavior == "ask"
    assert guard.check("Write", {"file_path": buf.value + "\\deck\\x.html"}, "deck").behavior == "allow"


def test_the_write_guard_on_posix_paths(tmp_path):
    """The guard with this system's own paths (on Linux, /tmp/...): the rules hold, and the path it hands back opens."""
    from deck_studio.config import generic_config
    from deck_studio.core.write_guard import create_guard
    kit = tmp_path / "Projeto"
    (kit / "deck" / "src" / "slides").mkdir(parents=True)
    slide = kit / "deck" / "src" / "slides" / "00-title.html"
    slide.write_text("<section></section>", encoding="utf-8")
    guard = create_guard(generic_config(kit))
    assert guard.check("Write", {"file_path": str(slide)}, "deck").behavior == "allow"
    assert guard.check("Write", {"file_path": str(kit / "deck" / "dist" / "deck.html")}, "deck").behavior == "deny"
    assert guard.check("Edit", {"file_path": str(kit / "qa" / "check_deck.py")}, "deck").behavior == "ask"
    assert guard.check("Write", {"file_path": str(tmp_path / "fora.txt")}, "deck").behavior != "allow"
    assert open(guard.write_path("Write", {"file_path": str(slide)}), encoding="utf-8").read() == "<section></section>"
