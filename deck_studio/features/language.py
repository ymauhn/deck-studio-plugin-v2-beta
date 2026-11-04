"""Deck language (pedido 2, 2026-11-04): an English and a Portuguese copy of the slides, and a switch between them.

The slides of the language on screen are always the ones in slidesDir (deck/src/slides), the only folder the deck's
build reads: the edits, the build, Exportar PDF and Publicar all work on them. Each language also keeps a copy in
<deck/src>/i18n/<lang>/, and <deck/src>/i18n/active.txt names the language in slidesDir (the project's base language
when it is missing: config "language", else English).

- GET /api/language: {active, base, languages: [{code, label, available}]}.
- POST /api/language {lang}: the switch. Under the turn lock: the slides in slidesDir are copied to i18n/<active>/,
  then i18n/<lang>/'s replace them, then the deck is rebuilt and reloaded. Files are copied, never moved, so a switch
  that stops halfway leaves every slide in one of the two folders. Undo of an older turn refuses (its files changed)
  until the deck is back in that turn's language.
- The translation itself is an ordinary chat turn (the UI sends translation_prompt()), so it has its diff and undo:
  the agent writes i18n/<lang>/, which is in the deck's allowed area."""
import shutil
from pathlib import Path

from fastapi import APIRouter, Request

from deck_studio.server.api import ApiError, json_body

router = APIRouter()
LANGUAGES = {"en": "Inglês", "pt": "Português"}
NAMES = {"en": "English", "pt": "Brazilian Portuguese"}


def _slides(state):
    return state.kit_root / state.config["slidesDir"]


def _folder(state):
    return _slides(state).parent / "i18n"


def base(state):
    lang = state.config.get("language")
    return lang if lang in LANGUAGES else "en"


def active(state):
    try:
        lang = (_folder(state) / "active.txt").read_text(encoding="utf-8").strip()
    except OSError:
        return base(state)
    return lang if lang in LANGUAGES else base(state)


def _html(folder):
    return sorted(Path(folder).glob("*.html")) if Path(folder).is_dir() else []


def payload(state):
    on = active(state)
    return {"active": on, "base": base(state),
            "languages": [{"code": c, "label": label, "available": c == on or bool(_html(_folder(state) / c))}
                          for c, label in LANGUAGES.items()]}


def note(state):
    """A line for the agent's message when the slides on screen are not in the project's base language."""
    on = active(state)
    if on == base(state):
        return ""
    return (f"\n\n(Deck Studio: the slides in {state.config['slidesDir']} are now the {NAMES[on]} version of the deck. "
            f"Keep their text in {NAMES[on]}.)")


def translation_prompt(state, lang):
    """The chat message that asks the agent for the translation."""
    src = state.config["slidesDir"]
    out = f"{Path(src).parent.as_posix()}/i18n/{lang}"
    return (f"Traduza o deck para {LANGUAGES[lang].lower()} ({NAMES[lang]}). Para cada arquivo .html em {src}/, "
            f"escreva {out}/ com o mesmo nome e o mesmo HTML, só com o texto visível traduzido. Mantenha as tags, "
            "classes, ids, atributos data-*, componentes, fórmulas, números e nomes próprios como estão. "
            f"Não mude nada em {src}/. No fim, diga quantos arquivos traduziu.")


@router.get("/api/language")
def get_language(request: Request):
    return payload(request.app.state.studio)


@router.get("/api/language/prompt/{lang}")
def get_prompt(lang: str, request: Request):
    if lang not in LANGUAGES:
        raise ApiError(400, "lang", "Idioma desconhecido.")
    return {"text": translation_prompt(request.app.state.studio, lang)}


@router.post("/api/language")
async def switch(request: Request):
    state = request.app.state.studio
    lang = (await json_body(request)).get("lang")
    if lang not in LANGUAGES:
        raise ApiError(400, "lang", "Idioma desconhecido.")
    on = active(state)
    if lang == on:
        return payload(state)
    target = _folder(state) / lang
    if not _html(target):
        raise ApiError(400, "missing", f"Ainda não há a versão em {LANGUAGES[lang].lower()}. Gere a tradução primeiro.")
    if state.turn_lock.locked():
        raise ApiError(409, "busy", "Espere o pedido em andamento terminar para trocar o idioma.")
    async with state.turn_lock:
        await state.publish_status()
        slides, keep = _slides(state), _folder(state) / on
        keep.mkdir(parents=True, exist_ok=True)
        for f in _html(keep):  # the copy of the language on screen is made again from the slides
            f.unlink()
        for f in _html(slides):
            shutil.copy2(f, keep / f.name)
        names = {f.name for f in _html(target)}
        for f in _html(slides):
            if f.name not in names:  # a slide only the other language has (its copy is in `keep`)
                f.unlink()
        for f in _html(target):
            shutil.copy2(f, slides / f.name)
        (_folder(state) / "active.txt").write_text(lang, encoding="utf-8")
    await state.publish_status()
    await state.builder.sources_changed([str(_folder(state) / "active.txt")])  # a full build, then the deck reloads
    return payload(state)
