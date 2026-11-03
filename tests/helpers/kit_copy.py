"""Disposable copies of the deck kit for tests: plain copies only, and deletion is guarded."""
import os
import shutil
import stat
import tempfile
import time
from pathlib import Path

REAL_KIT = Path(r"C:\Users\Yeonatan\OneDrive\Desktop\nexusgo_deck_kit")
PREFIX = "deck-studio-kit-"
PARTS = ["deck", "tools", "data", "source/thesis/dissertation.tex", "docs/FACTS.md", "qa/number_audit.md"]
SKIP = {Path("deck", p) for p in ("dist", "build/studio", "build/harness", "build/tikz-work")}


def make_kit_copy(src=None, extra=()):
    """Copy the kit parts the studio needs (plus `extra` kit-relative paths) into a new temp folder."""
    src = Path(src or os.environ.get("STUDIO_KIT") or REAL_KIT)
    root = Path(tempfile.mkdtemp(prefix=PREFIX))

    def ignore(folder, names):
        rel = Path(folder).relative_to(src)
        return [n for n in names if rel / n in SKIP]

    for part in [*PARTS, *extra]:
        s, d = src / part, root / part
        if s.is_dir():
            shutil.copytree(s, d, ignore=ignore)
        else:
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, d)
    return root


def remove_kit_copy(root):
    """Delete a copy made by make_kit_copy; anything else is refused."""
    r = Path(root).resolve()
    if r.parent != Path(tempfile.gettempdir()).resolve() or not r.name.startswith(PREFIX):
        raise ValueError(f"refusing to delete {root}")
    remove_tree(r)


def remove_tree(path, timeout=30):
    """Delete a folder, read-only files included. taskkill ends a server's process tree without waiting for it, so a
    build's esbuild.exe (or a TeX run) may still hold its files for a moment: Windows refuses to delete them until
    the process is gone, and the deletion is tried again until then."""
    def writable(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)

    end = time.monotonic() + timeout
    while True:
        try:
            return shutil.rmtree(path, onexc=writable)
        except OSError:
            if not os.path.exists(path):
                return
            if time.monotonic() > end:
                raise
            time.sleep(0.1)
