"""Jobs: Exportar PDF, Publicar and Regenerar Beamer (SPEC stories 50-53).

A job is the adapter's list of argv lists (config["jobs"][name]), run in order in the kit root and in the
background. Its output goes out live as `job` events: {id, name, state: "running"} at the start, one
{..., line} per output line, and {id, name, state: "ok" | "error", ms, file?, url?} at the end."""
import asyncio
import contextlib
import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from deck_studio.server.api import ApiError, json_body

CONFIRM = {"publish"}  # outward-facing: starts only with {"confirm": true}, which the UI sends after asking

router = APIRouter()


def running(state):
    return state.extras.setdefault("jobs", {})  # job name -> task of its run in progress


def dist_pdf(state, path):
    """The file at kit-relative `path` when it is a PDF right in the export's folder (deck/dist/*.pdf).

    The check is on the path as written, before any disk access: "..", drives and UNC paths never match."""
    rel = Path(path)
    if rel.parent != Path(state.config["jobOutputs"]["export-pdf"]).parent or rel.suffix.lower() != ".pdf":
        return None
    file = state.kit_root / rel
    return file if file.is_file() else None


async def run_lines(state, argv, on_line):
    """Run one command in the kit root, handing each output line to on_line; returns its exit code."""
    proc = await asyncio.create_subprocess_exec(
        shutil.which(argv[0]) or argv[0], *argv[1:], cwd=state.config["kitRoot"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        async for raw in proc.stdout:
            await on_line(raw.decode("utf-8", "replace").rstrip())
        return await proc.wait()
    except asyncio.CancelledError:  # the studio is closing: stop the command's whole process tree
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        raise


async def run_job(state, job_id, name, commands):
    # what this run needs from the config, read once: the deck's language may change while it runs
    cleans = [state.config.get("cleanBuild"), *state.config.get("otherCleanBuilds", [])]
    out = state.config["jobOutputs"].get(name)
    export_dir = Path(state.config["jobOutputs"].get("export-pdf", "deck/dist/x.pdf")).parent
    def say(**e):
        return state.events.publish("job", id=job_id, name=name, **e)

    t0 = time.perf_counter()
    ok = False
    try:
        await say(state="running")
        for argv in commands:
            await say(state="running", line="> " + subprocess.list2cmdline(argv))
            # the clean build writes deck/build as the studio builds do: it takes their turn, never runs beside one
            clean = argv in cleans
            async with state.builder.lock if clean else contextlib.nullcontext():
                code = await run_lines(state, argv, lambda line: say(state="running", line=line))
            if code != 0:  # the commands after a failed one never run
                await say(state="running", line=f"O comando saiu com o código {code}.")
                break
        else:
            ok = True
    except Exception as e:  # a missing program, say: the job still ends, as an error
        await say(state="running", line=str(e))
    finally:
        running(state).pop(name, None)
    end = {"state": "ok" if ok else "error", "ms": round((time.perf_counter() - t0) * 1000)}
    if ok and out and (state.kit_root / out).is_file():
        end["file"] = out
        if Path(out).parent == export_dir and Path(out).suffix.lower() == ".pdf":
            end["url"] = f"/api/jobs/files/{quote(out)}"
    await say(**end)


async def shutdown(state):
    """The studio is closing: running jobs stop, and run_lines stops their process trees."""
    tasks = list(running(state).values())
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


@router.post("/api/jobs/{name}", status_code=202)
async def start_job(name: str, request: Request):
    state = request.app.state.studio
    commands = state.config["jobs"].get(name)
    if commands is None:
        raise ApiError(404, "not-found", "Tarefa desconhecida.")
    body = await json_body(request)
    if name in CONFIRM and body.get("confirm") is not True:
        raise ApiError(400, "confirm", "Publicar exige confirmação.")
    if state.turn_lock.locked():  # an agent turn or a direct edit may have the deck half changed: never ship that
        raise ApiError(409, "busy", "Espere o pedido em andamento terminar: a tarefa usaria o deck no meio da mudança.")
    if name in running(state):
        raise ApiError(409, "busy", "Esta tarefa já está rodando.")
    job_id = str(uuid.uuid4())
    running(state)[name] = asyncio.create_task(run_job(state, job_id, name, commands))
    return {"jobId": job_id}


@router.get("/api/jobs/site")
def site(request: Request):
    """The URL of the site that Publicar updates, for its confirmation; null before the first publish."""
    state = request.app.state.studio
    try:
        url = json.loads((state.kit_root / state.config["publishSite"]).read_text(encoding="utf-8-sig"))["url"]
    except (OSError, ValueError, KeyError, TypeError):
        url = None
    return {"url": url, "paths": state.config.get("publishPaths", ["/"])}


@router.get("/api/jobs/files/{path:path}")
def job_file(path: str, request: Request):
    """An exported PDF, for the "Abrir" link; nothing outside deck/dist/*.pdf."""
    file = dist_pdf(request.app.state.studio, path)
    if not file:
        raise ApiError(404, "not-found", "Arquivo não encontrado.")
    return FileResponse(file, media_type="application/pdf", headers={"Cache-Control": "no-store"})
