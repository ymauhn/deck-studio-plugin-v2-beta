"""Cadastrar link de publicação (pedido de 04/11/2026): a project made by Deck Studio gets a Netlify site of its own,
and then a Publicar like the NEXUS-GO kit's.

POST /api/publish-site {name, create, confirm}: runs the project's deck/tools/publish_netlify.py register (copied from
the template when an older project lacks it), which keeps {id, name, url} in deck/tools/netlify-site.json; then the
config gains the publish job and its site file, so Publicar shows after the page reloads. create=true makes a new site
on Netlify, an outward action: it needs confirm=true, which the UI sends after asking."""
import shutil
import sys
from pathlib import Path

from fastapi import APIRouter, Request

from deck_studio.config import run_command
from deck_studio.server.api import ApiError, json_body
from deck_studio.templates import PROJECT

router = APIRouter()
TOOL = "deck/tools/publish_netlify.py"
SITE = "deck/tools/netlify-site.json"


def publish_job(config):
    """The publish job of a project: the clean build, then the tool."""
    return [config["cleanBuild"], [sys.executable, "-I", "-u", TOOL]]


@router.post("/api/publish-site")
async def register(request: Request):
    state = request.app.state.studio
    body = await json_body(request)
    name, create = body.get("name"), body.get("create") is True
    if state.config.get("format") != "html" or not (state.kit_root / "studio.json").is_file():
        raise ApiError(400, "not-a-project", "Só um projeto HTML feito pelo Deck Studio cadastra um link aqui.")
    if not isinstance(name, str) or not name.strip():
        raise ApiError(400, "name", "Dê o nome do site no Netlify (o que vem antes de .netlify.app).")
    if create and body.get("confirm") is not True:
        raise ApiError(400, "confirm", "Criar um site no Netlify exige confirmação.")
    if state.turn_lock.locked():
        raise ApiError(409, "busy", "Espere o pedido em andamento terminar.")
    tool = state.kit_root / TOOL
    if not tool.is_file():  # a project made before the tool was in the template
        tool.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PROJECT / TOOL, tool)
    argv = [sys.executable, "-I", "-u", TOOL, "register", "--name", name.strip(), *(["--create"] if create else [])]
    code, out, _ = await run_command(state.config, argv)
    if code != 0 or not (state.kit_root / SITE).is_file():
        raise ApiError(400, "netlify", out.strip().splitlines()[-1] if out.strip() else "O Netlify não respondeu.")
    state.config["jobs"]["publish"] = publish_job(state.config)
    state.config["publishSite"] = SITE
    url = next((line.split(" ", 1)[1] for line in out.splitlines() if line.startswith("registered ")), None)
    return {"url": url, "jobs": list(state.config["jobs"])}
