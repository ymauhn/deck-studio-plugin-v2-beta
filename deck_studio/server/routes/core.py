"""Core routes: the studio page, its static UI files, the studio deck and the status."""
import json
import secrets
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response, StreamingResponse

UI = Path(__file__).resolve().parents[2] / "ui"
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png"}

router = APIRouter()


def ui_urls(folder, suffix):
    """URLs of the UI files ui/<folder>/*.<suffix>, by name."""
    return [f"/ui/{folder}/{f.name}" for f in sorted((UI / folder).glob(f"*.{suffix}"))]


def send_file(file):
    file = Path(file)
    if file.suffix not in TYPES or not file.is_file():
        raise HTTPException(404)
    return FileResponse(file, media_type=TYPES[file.suffix], headers={"Cache-Control": "no-cache"})


@router.get("/")
def index():
    return send_file(UI / "index.html")


@router.get("/ui/fonts.css")
def fonts(request: Request):
    """The deck's embedded font faces, from the kit; an empty stylesheet for a deck on system fonts."""
    state = request.app.state.studio
    if not state.config["fontsCss"]:
        return Response("", media_type=TYPES[".css"], headers={"Cache-Control": "no-cache"})
    return send_file(state.kit_root / state.config["fontsCss"])


@router.get("/ui/{path:path}")
def ui_file(path: str):
    file = (UI / path).resolve()
    if not file.is_relative_to(UI):
        raise HTTPException(404)
    return send_file(file)


@router.get("/api/status")
def status(request: Request):
    """The studio's state, and the project it edits (the UI reads it once, as studio.project)."""
    state = request.app.state.studio
    project = {k: state.config[k] for k in ("title", "format", "startMode", "beamerStart", "provenance")}
    return {**state.status(), "project": {**project, "jobs": list(state.config["jobs"])}}


@router.get("/deck")
async def deck(request: Request):
    """The studio deck, with picker.js and then every ui/deck/*.js injected; built again first when its sources
    changed outside the studio. Its CSP runs only the shell's own scripts (their hashes, from the studio build) and
    ours (a nonce per response): a script that a slide holds, written by the agent with no approval card, never runs
    with the studio's origin, where it could answer approval cards or start Publicar. Nor does the deck load anything
    from another server (an image or a CSS url would tell it what the agent put in its address), except the Google
    Fonts that the NEXUS-GO shell links."""
    state = request.app.state.studio
    await state.builder.current()
    out = state.kit_root / state.config["studioOut"]
    try:
        html = out.read_text(encoding="utf-8")
        hashes = json.loads((out.parent / "csp.json").read_text(encoding="utf-8"))["scripts"]
    except (OSError, ValueError, KeyError):
        return PlainTextResponse(f"O deck ainda não compilou.\n\n{state.builder.state['error'] or ''}", 503)
    nonce = secrets.token_urlsafe(18)
    scripts = "".join(f'<script type="module" nonce="{nonce}" src="{url}"></script>\n'
                      for url in ["/ui/picker.js", *ui_urls("deck", "js")])
    end = html.rfind("</body>")  # the last one: the engine bundle itself contains the string '</body>'
    end = len(html) if end < 0 else end
    csp = (f"default-src 'self' data:; script-src 'nonce-{nonce}' {' '.join(hashes)}; "
           "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' data: https://fonts.gstatic.com; "
           "object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'")
    return HTMLResponse(html[:end] + scripts + html[end:],
                        headers={"Cache-Control": "no-store", "Content-Security-Policy": csp})


@router.get("/api/events")
async def events(request: Request):
    """Server-Sent Events: the status first, then every event the studio publishes."""
    state = request.app.state.studio

    async def stream():
        async for event in state.events.stream({"type": "status", **state.status()}):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})


@router.get("/api/ui-features")
def ui_features():
    """The UI feature modules: app.js imports `app` (and links `css`), /deck injects `deck`."""
    return {"app": ui_urls("features", "js"), "deck": ui_urls("deck", "js"), "css": ui_urls("features", "css")}
