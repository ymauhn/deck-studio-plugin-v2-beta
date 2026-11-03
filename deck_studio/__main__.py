"""Deck Studio CLI:
python -m deck_studio [--kit PATH] [--port 0] [--data DIR] [--config JSON_FILE] [--fake-agent SCENARIOS_DIR] [--no-open]
                      [--home DIR] [--parent-pid PID]
"""
import os

# first: no API key or Claude Code variable reaches this process or any child (SDK, claude CLI, builds)
for _name in [n for n in os.environ if n.upper().startswith(("ANTHROPIC_", "CLAUDE"))]:
    del os.environ[_name]

import argparse  # noqa: E402
import asyncio  # noqa: E402
import ctypes  # noqa: E402
import msvcrt  # noqa: E402
import socket  # noqa: E402
import sys  # noqa: E402
import threading  # noqa: E402
import webbrowser  # noqa: E402
from ctypes import wintypes  # noqa: E402
from pathlib import Path  # noqa: E402

import uvicorn  # noqa: E402

from deck_studio import projects  # noqa: E402
from deck_studio.config import load_config  # noqa: E402
from deck_studio.server.app import create_app  # noqa: E402
from deck_studio.server.state import StudioState  # noqa: E402

DEFAULT_KIT = r"C:\Users\Yeonatan\OneDrive\Desktop\nexusgo_deck_kit"
DEFAULT_DATA = Path(os.environ.get("LOCALAPPDATA", ".")) / "deck-studio"  # the default kit's, and the home


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="python -m deck_studio", description="Deck Studio: local AI editor for slide decks.")
    p.add_argument("--kit", default=DEFAULT_KIT, help="deck kit root")
    p.add_argument("--port", type=int, default=0, help="0 picks a free port")
    p.add_argument("--data", help="app data dir (default: %%LOCALAPPDATA%%\\deck-studio; a project's own, under --home)")
    p.add_argument("--config", help="JSON file merged over the deck adapter config")
    p.add_argument("--fake-agent", help="scenarios dir: use the scripted agent instead of Claude")
    p.add_argument("--no-open", action="store_true", help="do not open the browser")
    p.add_argument("--home", help="Deck Studio's home: projects.json and the projects' data dirs (default: --data, "
                                  "else %%LOCALAPPDATA%%\\deck-studio)")
    p.add_argument("--parent-pid", type=int, help="exit when this process ends (a project's studio and its parent)")
    return p.parse_args(argv)


def watch_parent(pid):
    """Exit as soon as process `pid` ends, however it ends: a project's studio never outlives the studio that started
    it, even when that one is killed without a chance to stop its children."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    handle = kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE: enough to wait on it
    if not handle:  # it has ended already
        os._exit(0)

    def wait():
        kernel32.WaitForSingleObject(handle, 0xFFFFFFFF)  # INFINITE
        os._exit(0)

    threading.Thread(target=wait, name="parent-watchdog", daemon=True).start()


def lock_data_dir(data_dir):
    """The open studio.lock of this data dir, locked while this studio runs; None when another studio holds it.

    The lock is on a byte far past the file's text, which is the running studio's URL, so others can read it."""
    data_dir.mkdir(parents=True, exist_ok=True)
    fd = os.open(data_dir / "studio.lock", os.O_RDWR | os.O_CREAT | os.O_BINARY)
    os.lseek(fd, 1 << 30, os.SEEK_SET)
    try:
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)  # the OS drops it when this process ends, however it ends
    except OSError:
        os.close(fd)
        return None
    os.ftruncate(fd, 0)
    return fd


def default_data(kit, home):
    """The data dir when --data is not given: the default kit's, or for a project made by Deck Studio its own,
    <home>/projects/<slug> (on the default kit's, its chats and history would mix with NEXUS-GO's). None for a project
    the registry does not have."""
    if not (Path(kit) / "studio.json").is_file():
        return DEFAULT_DATA
    here = os.path.normcase(str(Path(kit).resolve()))
    slug = next((p["slug"] for p in projects.registry(home)
                 if os.path.normcase(str(Path(p["path"]).resolve())) == here), None)
    return home / "projects" / slug if slug else None


async def main(args):
    if args.parent_pid:
        watch_parent(args.parent_pid)
    home = Path(args.home or args.data or DEFAULT_DATA)
    data = Path(args.data) if args.data else default_data(args.kit, home)
    if data is None:
        print("Esta pasta é um projeto do Deck Studio fora da lista de projetos. Para abri-lo, dê a ele uma pasta de "
              "dados só dele com --data.", file=sys.stderr, flush=True)
        return 1
    # one studio per data dir: two would run turns at once and overwrite each other's chats and history
    lock = lock_data_dir(data)
    if lock is None:
        print(f"O Deck Studio já está aberto com esta pasta de dados ({data}).", file=sys.stderr, flush=True)
        url = (data / "studio.lock").read_text(encoding="utf-8")
        if not url:  # it is still starting
            return 1
        print(f"DECK_STUDIO_URL={url}", flush=True)
        if not args.no_open:
            webbrowser.open(url)
        return 0
    sock = socket.socket()
    sock.bind(("127.0.0.1", args.port))  # never another interface
    port = sock.getsockname()[1]
    state = StudioState(load_config(args.kit, args.config), data, port, fake_agent=args.fake_agent, home=home,
                        config_path=args.config)
    config = uvicorn.Config(create_app(state), log_level="warning", access_log=False, timeout_graceful_shutdown=1)
    server = uvicorn.Server(config)
    serving = asyncio.create_task(server.serve(sockets=[sock]))
    while not server.started:
        if serving.done():
            return await serving
        await asyncio.sleep(0.02)
    url = f"http://127.0.0.1:{port}/?t={state.token}"
    os.lseek(lock, 0, os.SEEK_SET)
    os.write(lock, url.encode("utf-8"))
    print(f"DECK_STUDIO_URL={url}", flush=True)
    if not args.no_open:
        webbrowser.open(url)
    await serving


if __name__ == "__main__":
    sys.exit(asyncio.run(main(parse_args())))
