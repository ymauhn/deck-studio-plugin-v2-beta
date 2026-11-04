"""Projetos (docs/IMPORT.md "HTTP"): the projects this studio can open, and a new talk from a PDF.

- GET /api/projects: {current: {name, path}, projects, projectsFolder}. The default kit comes first (unless it is
  this studio's own), then the imported projects, newest first; each has `url` while its studio runs, `here` when
  it is this studio's, and `missing` when its folder is gone. projectsFolder is where new projects go
  (config["projectsFolder"] in tests).
- POST /api/projects/import: the raw PDF (x-file-name: its URL-encoded name) and the query {name, format, language,
  folder?, notes?}. It fills the template into the folder, saves the PDF in context/, extracts it into
  context/<slug>/, registers the project, starts its studio and sends that studio's first chat the request to build
  the talk (config["importMessage"], or projects.MESSAGE, then the author's notes). Answers 201 {project, url,
  warning?}; the URL opens that chat (#chat=<id>), and `warning` says when the PDF has almost no text (a scan).
  A refusal is a 400 {error, message} in pt-BR and leaves nothing behind; a `projects` event {step: "opening", name}
  says when the extraction is done. With no folder, or the default one, it goes to the first free of
  <projects folder>\\<Nome>, "<Nome> (2)"...
- POST /api/projects/open {path}: a registered project or the default kit -> {url} of its studio, on the chat whose
  turn runs, else the one used last.
- POST /api/projects/remove {path}: a registered project leaves the list -> {path}; its folder and data stay.
A project's studio is a child of the studio that starts it, or the one already running on its data dir."""
import asyncio
import os
import re
import sys
from pathlib import Path, PureWindowsPath
from urllib.parse import unquote

from fastapi import APIRouter, Request
from starlette.datastructures import UploadFile

from deck_studio import projects
from deck_studio.__main__ import DEFAULT_KIT
from deck_studio.core import plataforma
from deck_studio.features.files import plain
from deck_studio.server.api import ApiError, json_body

router = APIRouter()
LIMIT = 100 * 1024 * 1024  # bytes of PDF, and of all the files of a folder together
FILES_LIMIT = 200  # files in a folder import
# what a folder import keeps: the sources the agent reads and the images it may put on slides
KEPT = {".pdf", ".md", ".txt", ".tex", ".bib", ".csv", ".json", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif"}
IMAGES = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif"}
BUILTIN = "NEXUS-GO (kit da defesa)"  # the default kit, in the list; its studio's data dir is the home
NOT_EMPTY = "Esta pasta já existe e tem arquivos. Escolha uma pasta nova ou vazia."
EXAMPLE = "C:\\Users\\voce\\Deck Studio\\Projeto" if plataforma.WINDOWS else "/home/voce/Deck Studio/Projeto"
# Windows paths stop at 260 characters here (LongPathsEnabled is 0): the project's own paths add up to about 75
# (context/<slug>/figuras/p001-1.png, context/<pdf>), and the agent's files need room too
FOLDER_LIMIT = 150
TEX_UNSAFE = re.compile(r"[%~${}]")  # latexmk refuses a path with % ~ $, and braces break TeX's file names
DISK = re.compile(r"(?:[\\/]{2}[?.][\\/])?[A-Za-z]:[\\/]")  # C:\... or \\?\C:\...: a disk of this PC, not a share
if not plataforma.WINDOWS:
    DISK = re.compile(r"/(?!/)")  # an absolute path
NOTES_LIMIT = 1000  # characters: they travel in the query
SCANNED_WORDS = 5  # per page, at most: a scan has no text, or a stamp's few words
SCANNED = ("Este PDF quase não tem texto selecionável: parece escaneado. O agente vai ler as páginas como imagens, o que "
           "demora mais.")
START = 60  # seconds a studio may take to start


def lock(state):
    """One import or open at a time: slugs, folders and children are decided under it."""
    return state.extras.setdefault("projects-lock", asyncio.Lock())


def children(state):
    """The project studios this studio started: normcased kit path -> (process, URL)."""
    return state.extras.setdefault("projects-children", {})


def real(path):
    """The folder `path` names, resolved, in one spelling. resolve() keeps the \\\\?\\ prefix on some spellings (a
    name that ends in a space or dots, or one given with the prefix), and no comparison would then match."""
    return Path(re.sub(r"^\\\\\?\\(?=[A-Za-z]:\\)", "", str(Path(path).resolve())))


def key(path):
    return os.path.normcase(str(real(path)))


def used(path):
    """Whether `path` is taken: a file, or a folder with something in it."""
    try:
        return path.exists() and not (path.is_dir() and not any(path.iterdir()))
    except OSError:
        return True


def projects_folder(state):
    """Where new projects go: %USERPROFILE%\\Deck Studio, or the config's projectsFolder."""
    return Path(state.config.get("projectsFolder") or Path.home() / "Deck Studio")


def default_folder(state, name):
    """<projects folder>\\<name>, without the characters LaTeX refuses in a path (as the panel suggests it)."""
    return projects_folder(state) / (" ".join(TEX_UNSAFE.sub("", name).split()).strip(" .") or "Projeto")


def free(folder):
    """`folder`, or "<folder> (2)", "(3)"...: the first one absent or empty."""
    path, n = folder, 1
    while used(path):
        n += 1
        path = folder.with_name(f"{folder.name} ({n})")
    return path


def checked_folder(state, folder, known):
    """The new project's folder: absolute and on a disk of this PC, short enough for Windows, without what LaTeX
    refuses, absent or empty, and outside the kits and the registered projects."""
    if not PureWindowsPath(folder).is_absolute():
        raise ApiError(400, "bad-folder", f"Informe a pasta pelo caminho completo, como {EXAMPLE}.")
    # a share (\\localhost\C$\...) names any folder under another spelling; it is refused before resolve(), which
    # would reach it over the network, and after (a mapped drive resolves to its share)
    path = real(folder) if DISK.match(folder) else None
    if not path or not DISK.match(str(path)):
        raise ApiError(400, "bad-folder", f"Escolha uma pasta num disco deste computador, como {EXAMPLE}.")
    if len(str(path)) > FOLDER_LIMIT:
        raise ApiError(400, "long-folder", f"O caminho da pasta passa de {FOLDER_LIMIT} caracteres, longo demais para "
                                           "o Windows. Escolha uma pasta ou um nome mais curto.")
    if TEX_UNSAFE.search(str(path)):
        raise ApiError(400, "bad-folder", "O caminho da pasta não pode ter os caracteres % ~ $ { }: o LaTeX não "
                                          "compila nele.")
    if used(path):
        raise ApiError(400, "folder-not-empty", NOT_EMPTY)
    for root in [state.kit_root, Path(DEFAULT_KIT), *(Path(p["path"]) for p in known)]:
        if path.is_relative_to(real(root)):
            raise ApiError(400, "folder-inside", "Esta pasta fica dentro de um projeto ou do kit. Escolha uma fora deles.")
    return path


def passthrough(state):
    """This studio's own --fake-agent and --config: in tests, its children are scripted and safe too."""
    extra = ["--fake-agent", str(state.fake_agent.resolve())] if state.fake_agent else []
    return [*extra, "--config", str(Path(state.config_path).resolve())] if state.config_path else extra


async def studio_url(state, kit, data_dir):
    """The URL of the studio on `kit`: a child of ours, one that runs on its data dir (another studio started it),
    or a new child. Call it under lock(state)."""
    child = children(state).get(key(kit))
    if child and child[0].poll() is None:
        return child[1]
    url = await asyncio.to_thread(projects.running_url, data_dir, START)  # one that starts gives its URL in moments
    if url:
        return url
    proc, url, _ = await asyncio.to_thread(projects.start, kit, data_dir, state.home.resolve(), passthrough(state),
                                           START)
    if not url:  # its last lines went to this studio's stderr
        projects.stop_tree(proc.pid)
        raise ApiError(500, "no-studio", "O studio do projeto não abriu. Tente abrir de novo em Projetos.")
    children(state)[key(kit)] = (proc, url)
    return url


def running(state, kit, data_dir):
    child = children(state).get(key(kit))
    url = child[1] if child and child[0].poll() is None else projects.running_url(data_dir)
    return {"running": bool(url), "url": url}


@router.get("/api/projects")
def list_projects(request: Request):
    state = request.app.state.studio
    here = key(state.kit_root)
    on_default = here == key(DEFAULT_KIT)
    builtin = [] if on_default else [{"name": BUILTIN, "path": DEFAULT_KIT, "format": "html", "builtin": True,
                                      **running(state, DEFAULT_KIT, state.home)}]
    imported = [{**p, **running(state, p["path"], state.home / "projects" / p["slug"]),
                 **({"here": True} if key(p["path"]) == here else {}),
                 **({} if Path(p["path"]).is_dir() else {"missing": True})}
                for p in reversed(projects.registry(state.home))]
    return {"current": {"name": BUILTIN if on_default else state.config["title"], "path": str(state.kit_root)},
            "projects": [*builtin, *imported], "projectsFolder": str(projects_folder(state))}


def context_path(name):
    """A file's path inside context/ as the browser sends it (a folder's relative path): each part plain, no "..",
    at most 4 levels; None when it cannot be used."""
    parts = [p for p in re.split(r"[\\/]+", name or "") if p]
    if not parts or len(parts) > 4 or any(p in (".", "..") or not plain(p) for p in parts):
        return None
    return "/".join(parts)


@router.post("/api/projects/import-files", status_code=201)
async def import_files(request: Request, name: str = "", format: str = "", language: str = "", folder: str = "",
                       notes: str = ""):
    """A new talk from a folder, or several files: multipart/form-data with a `files` field per file, whose file
    name is its path in the folder (the browser's webkitRelativePath). Every PDF is extracted into
    context/<its slug>/, as the single-PDF import does; the other files go to context/ as they are."""
    state = request.app.state.studio
    form = await request.form(max_files=FILES_LIMIT + 1, max_part_size=LIMIT)
    uploads = [f for f in form.getlist("files") if isinstance(f, UploadFile)]
    name, notes = name.strip(), notes.strip()
    _check_fields(name, format, language, notes)
    if not uploads:
        raise ApiError(400, "no-files", "Escolha uma pasta ou alguns arquivos.")
    if len(uploads) > FILES_LIMIT:
        raise ApiError(400, "too-many", f"A pasta passa de {FILES_LIMIT} arquivos.")
    files, skipped, total = {}, [], 0
    for upload in uploads:
        rel = context_path(upload.filename)
        if rel is None or Path(rel).suffix.lower() not in KEPT:
            skipped.append(upload.filename or "?")
            continue
        data = await upload.read()
        total += len(data)
        if total > LIMIT:
            raise ApiError(400, "too-large", "Os arquivos passam de 100 MB juntos.")
        if rel.lower().endswith(".pdf") and not data.startswith(b"%PDF-"):
            raise ApiError(400, "not-pdf", f"{rel} não é um PDF.")
        files[rel] = data
    if not files:
        raise ApiError(400, "no-files", "Nenhum arquivo da pasta serve: use PDF, .md, .tex, .bib, .txt ou imagens.")
    pdfs = [rel for rel in files if rel.lower().endswith(".pdf")]

    def write(target, slug):
        projects.create_from_files(target, name, slug, format, language, files, pdfs[0] if pdfs else "")

    extracted = {}  # pdf -> its folder in context/

    async def extract(target, slug):
        taken, infos = set(), []
        for pdf in pdfs:
            out = projects.slug_of(Path(pdf).stem, taken | {slug}) if len(pdfs) > 1 else slug
            taken.add(out)
            extracted[pdf] = out
            infos.append(await projects.extract(target / "context" / pdf, target / "context" / out))
        projects.point_to_sources(target, slug, extracted)
        return infos

    def message(slug, scanned):
        lines = []
        for rel in sorted(files):
            if rel in extracted:
                lines.append(f"- `context/{rel}`: o texto em `context/{extracted[rel]}/texto.md`, as figuras em "
                             f"`context/{extracted[rel]}/figuras`")
            else:
                kind = "imagem" if Path(rel).suffix.lower() in IMAGES else "texto"
                lines.append(f"- `context/{rel}` ({kind})")
        text = state.config.get("importFolderMessage", projects.FOLDER_MESSAGE).format(
            format_name=projects.FORMATS[format], language=projects.LANGUAGES[language][2], files="\n".join(lines))
        for pdf, scan_ in zip(pdfs, scanned):
            if scan_:
                text += (f"\n\nO PDF `context/{pdf}` quase não tem texto selecionável (parece escaneado): leia as "
                         "páginas dele com a ferramenta Read.")
        if skipped:
            text += f"\n\nFicaram de fora (tipo não aceito): {', '.join(sorted(skipped)[:20])}."
        return text

    result = await _open_new(state, name, format, language, folder, notes, write, extract, message)
    if skipped:
        result["skipped"] = sorted(skipped)
    return result


def _check_fields(name, format, language, notes):
    if not plain(name):
        raise ApiError(400, "bad-name", 'Dê um nome ao projeto, sem os caracteres / \\ : * ? " < > |.')
    if format not in projects.FORMATS:
        raise ApiError(400, "bad-format", "Escolha o formato: HTML ou Beamer.")
    if language not in projects.LANGUAGES:
        raise ApiError(400, "bad-language", "Escolha o idioma dos slides: português ou inglês.")
    if len(notes) > NOTES_LIMIT:
        raise ApiError(400, "bad-notes", f"As instruções para o agente passam de {NOTES_LIMIT} caracteres.")


def scan(info):
    """Whether an extracted PDF has almost no text: a scan, which the agent reads as page images."""
    return info.get("words", 0) < SCANNED_WORDS * max(1, info.get("pages", 1))


async def _open_new(state, name, format, language, folder, notes, write, extract, message):
    """The steps both imports share: the folder (the suggested one, or the author's), the slug, the files (write),
    the extraction (extract -> infos), the registry, the project's studio and its first request (message(slug,
    scanned), then the author's notes); `scanned` says, per PDF, whether it looks scanned. Anything that fails
    leaves nothing behind."""
    async with lock(state):
        known = projects.registry(state.home)
        default = default_folder(state, name)
        if not folder or os.path.normcase(os.path.normpath(folder)) == os.path.normcase(default):
            folder = str(free(default))  # the suggested folder: a second import of a name goes to "<Nome> (2)"
        target = checked_folder(state, folder, known)
        slug = projects.reserve(state.home, name, {p["slug"] for p in known})
        data_dir, existed = state.home / "projects" / slug, target.exists()

        def undo(folder_too=True):  # nothing is left behind: the folder as it was, and the slug free again
            if folder_too:
                projects.discard(target, existed)
            try:
                data_dir.rmdir()
            except OSError:
                pass

        try:
            await asyncio.to_thread(write, target, slug)
        except FileExistsError:  # files came meanwhile: nothing was written, and those files are not ours
            undo(folder_too=False)
            raise ApiError(400, "folder-not-empty", NOT_EMPTY) from None
        except OSError as e:
            undo()
            print(f"Deck Studio: o projeto não foi criado em {target}: {e}", file=sys.stderr, flush=True)
            raise ApiError(400, "folder-error", "Não foi possível criar o projeto nesta pasta. Confira se o disco "
                                                "existe e se você pode gravar nela.") from None
        try:
            infos = await extract(target, slug)
            project = projects.entry(name, slug, target, format, language)
            await asyncio.to_thread(projects.register, state.home, project)
        except OSError as e:  # the registry could not be written
            undo()
            print(f"Deck Studio: o projeto {target} não entrou na lista: {e}", file=sys.stderr, flush=True)
            raise ApiError(500, "no-register", "O projeto não entrou na lista de projetos. Tente de novo.") from None
        except BaseException:
            undo()
            raise
        await state.events.publish("projects", step="opening", name=name)
        url = await studio_url(state, target, data_dir)
    scanned = [scan(i) for i in infos]
    text = message(slug, scanned)
    if notes:
        text += f"\n\nInstruções do autor: {notes}"
    try:
        chat = await asyncio.to_thread(projects.send_first, url, text)
    except OSError:
        raise ApiError(500, "no-request", "O projeto abriu, mas o pedido não chegou ao agente. Abra o projeto em "
                                          "Projetos e peça a apresentação no chat.") from None
    return {"project": project, "url": f"{url}#chat={chat}", **({"warning": SCANNED} if any(scanned) else {})}


@router.post("/api/projects/import", status_code=201)
async def import_pdf(request: Request, name: str = "", format: str = "", language: str = "", folder: str = "",
                     notes: str = ""):
    state = request.app.state.studio
    pdf = bytearray()
    async for chunk in request.stream():  # read to the end, so the client always gets the answer
        if len(pdf) <= LIMIT:
            pdf += chunk
    try:
        file_name = unquote(request.headers.get("x-file-name", ""), errors="strict")
    except ValueError:
        file_name = ""
    name, notes = name.strip(), notes.strip()
    _check_fields(name, format, language, notes)
    if not plain(file_name) or not file_name.lower().endswith(".pdf"):
        raise ApiError(400, "bad-file", "Escolha um arquivo .pdf.")
    if len(pdf) > LIMIT:
        raise ApiError(400, "too-large", "O PDF passa de 100 MB.")
    if not pdf.startswith(b"%PDF-"):
        raise ApiError(400, "not-pdf", "Este arquivo não é um PDF.")
    saved = projects.pdf_name(file_name)

    def write(target, slug):
        projects.create(target, name, slug, format, language, saved, bytes(pdf))

    async def extract(target, slug):
        return [await projects.extract(target / "context" / saved, target / "context" / slug)]

    def message(slug, scanned):
        text = state.config.get("importMessage", projects.MESSAGE).format(
            pdf=f"context/{saved}", format=format, format_name=projects.FORMATS[format],
            language=projects.LANGUAGES[language][2], text=f"context/{slug}/texto.md", figures=f"context/{slug}/figuras")
        if scanned[0]:
            text += (f"\n\nO PDF quase não tem texto selecionável (parece escaneado): leia as páginas de "
                     f"`context/{saved}` com a ferramenta Read.")
        return text

    return await _open_new(state, name, format, language, folder, notes, write, extract, message)


@router.post("/api/projects/open")
async def open_project(request: Request):
    state = request.app.state.studio
    path = (await json_body(request)).get("path")
    if not isinstance(path, str) or not path:
        path = None
    if path and key(path) == key(DEFAULT_KIT):
        kit, data_dir = Path(DEFAULT_KIT), state.home
    else:
        found = path and next((p for p in projects.registry(state.home) if key(p["path"]) == key(path)), None)
        if not found:
            raise ApiError(404, "not-found", "Este projeto não está na lista de projetos.")
        kit, data_dir = Path(found["path"]), state.home / "projects" / found["slug"]
    if not kit.is_dir():
        raise ApiError(404, "missing", f"A pasta do projeto não existe mais: {kit}")
    async with lock(state):
        url = await studio_url(state, kit, data_dir)
    chat = await asyncio.to_thread(projects.last_chat, url)  # a tab with no chat named would open a new, empty one
    return {"url": f"{url}#chat={chat}" if chat else url}


@router.post("/api/projects/remove")
async def remove_project(request: Request):
    state = request.app.state.studio
    path = (await json_body(request)).get("path")
    gone = isinstance(path, str) and path and await asyncio.to_thread(
        projects.unregister, state.home, lambda p: key(p["path"]) == key(path))
    if not gone:
        raise ApiError(404, "not-found", "Este projeto não está na lista de projetos.")
    return {"path": gone[0]["path"]}


async def shutdown(state):
    """The studios this one started end with it (--parent-pid covers a studio that is killed)."""
    for proc, _ in children(state).values():
        if proc.poll() is None:
            await asyncio.to_thread(projects.stop_tree, proc.pid)
