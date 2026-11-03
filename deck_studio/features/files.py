"""Files pane (SPEC stories 45-49): the folders the agent can use (GET /api/files), their images for thumbnails
(GET /api/files/image) and uploads into context/ (POST /api/files/upload)."""
import itertools
import os
import posixpath
import re
from pathlib import Path, PureWindowsPath
from urllib.parse import unquote

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from deck_studio.beamer.engine import discover_projects
from deck_studio.server.api import ApiError

router = APIRouter()
LIMIT = 50 * 1024 * 1024  # bytes per upload
IMAGES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp",
          ".svg": "image/svg+xml"}
NOT_PLAIN = re.compile(r'[<>:"/\\|?*\x00-\x1f]|[. ]$')  # separators, drives, streams, wildcards, "..", trailing dot


def plain(name):
    """A plain Windows file name: one path segment that names nothing but itself."""
    return 0 < len(name) <= 200 and not NOT_PLAIN.search(name) and not PureWindowsPath(name).is_reserved()


def roots(state):
    """The folders the pane lists, as {kind, path, folder, readOnly}: `path` is what the UI shows and sends back.
    The user skills (the config's readDirs) and the hand-written Beamer decks are only listed; in a Beamer project
    (an imported PDF's), its deck is the project's own work and not marked read-only."""
    c, kit = state.config, state.kit_root
    own = [("slides", c["slidesDir"]), ("images", c["imagesDir"]), ("context", c["contextDir"]), ("skills", ".claude/skills")]
    beamer = dict.fromkeys(posixpath.dirname(p["rel"]) for p in discover_projects(kit) if p["kind"] == "handwritten")
    return [*({"kind": k, "path": rel, "folder": kit / rel, "readOnly": False} for k, rel in own),
            *({"kind": "user-skills", "path": from_home(Path(d)), "folder": Path(d), "readOnly": True} for d in c["readDirs"]),
            *({"kind": "beamer", "path": rel, "folder": kit / rel, "readOnly": c.get("format") != "beamer"}
              for rel in beamer)]


def from_home(folder):
    """~/... for a folder in the user's home, else its absolute path."""
    return f"~/{folder.relative_to(Path.home()).as_posix()}" if folder.is_relative_to(Path.home()) else folder.as_posix()


def locate(state, path):
    """The root that holds `path`, and the file or folder it names. Paths are root/plain/names only, so nothing
    outside the roots can be named; links inside a root are followed, as its owner set them up."""
    for root in roots(state):
        rest = path[len(root["path"]) + 1:].split("/") if path.startswith(root["path"] + "/") else []
        if (path == root["path"] or rest) and all(map(plain, rest)):
            return root, root["folder"].joinpath(*rest)
    raise ApiError(403, "outside", "Esta pasta não está no painel de arquivos.")


@router.get("/api/files")
def list_files(request: Request, dir: str = ""):
    """No `dir`: the roots. Otherwise the entries of that folder, folders first; a root not created yet is empty."""
    state = request.app.state.studio
    if not dir:
        return [{"name": r["path"], "path": r["path"], "dir": True, "kind": r["kind"], "readOnly": r["readOnly"]}
                for r in roots(state)]
    root, folder = locate(state, dir)
    if not folder.is_dir():
        if folder == root["folder"]:
            return []
        raise ApiError(404, "not-found", "Pasta não encontrada.")
    items = sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    return [{"name": p.name, "path": f"{dir}/{p.name}", "dir": p.is_dir()} for p in items]


@router.get("/api/files/image")
def image(request: Request, path: str = ""):
    """An image in the roots, for the thumbnails. Sandboxed: an SVG opened by itself runs no script."""
    _, file = locate(request.app.state.studio, path)
    media = IMAGES.get(file.suffix.lower())
    if not media or not file.is_file():
        raise ApiError(404, "not-found", "Imagem não encontrada.")
    return FileResponse(file, media_type=media, headers={"Content-Security-Policy": "sandbox", "Cache-Control": "no-cache"})


@router.post("/api/files/upload", status_code=201)
async def upload(request: Request):
    """The raw body, named by the x-file-name header (URL-encoded UTF-8), saved as a new file in context/."""
    state = request.app.state.studio
    try:
        name = unquote(request.headers.get("x-file-name", ""), errors="strict")
    except ValueError:
        name = ""
    if not plain(name):
        raise ApiError(400, "bad-name", "Nome de arquivo inválido.")
    data = bytearray()
    async for chunk in request.stream():  # read to the end, so the client always gets the answer
        if len(data) <= LIMIT:
            data += chunk
    if len(data) > LIMIT:
        raise ApiError(413, "too-large", "O arquivo passa de 50 MB.")
    file = save_new(state.kit_root / state.config["contextDir"], name, data)
    return {"name": file.name, "path": f"{state.config['contextDir']}/{file.name}"}


def save_new(folder, name, data):
    """Write `data` as folder/name, or as "name (2).ext", "(3)"... when the name is taken: never overwrites."""
    folder.mkdir(parents=True, exist_ok=True)
    stem, ext = os.path.splitext(name)
    for n in itertools.count(1):
        file = folder / (name if n == 1 else f"{stem} ({n}){ext}")
        try:
            with open(file, "xb") as f:  # exclusive create: a file made meanwhile is never replaced
                f.write(data)
            return file
        except FileExistsError:
            pass
