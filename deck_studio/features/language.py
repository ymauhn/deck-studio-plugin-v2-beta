"""Deck language (pedido 2, 2026-11-04): English and Portuguese versions of the deck, and a switch between them.

A language comes in one of two layouts:
- a tree of its own, named by the config's languageTrees (NEXUS-GO's deck/src-pt, built with `build.mjs --pt`): the
  switch points the studio at it, replacing the config keys the tree gives (slidesDir, the builds, the jobs and their
  outputs), so the studio shows, selects, edits, builds, exports and publishes that version; nothing is copied. The
  choice is kept in the settings ("language");
- a copy made by "Traduzir" in <deck/src>/i18n/<lang>/, for a language without a tree: the slides of the language on
  screen are always the ones in the base slidesDir, the only folder the build reads, and <deck/src>/i18n/active.txt
  names it (the base language when it is missing: config "language", else English). The switch copies, never moves,
  under the turn lock: slidesDir to i18n/<active>/, then i18n/<lang>/ to slidesDir. Undo of an older turn refuses
  (its files changed) until the deck is back in that turn's language.

- GET /api/language: {active, base, languages: [{code, label, available, tree}]}.
- POST /api/language {lang}: the switch; then a full build and a deck reload.
- The translation is an ordinary chat turn (the UI sends translation_prompt()), with its diff and undo: the agent
  writes i18n/<lang>/, inside the deck's allowed area. The UI offers it only for a language that is neither the base
  nor a tree."""
import copy
import shutil
from pathlib import Path

from fastapi import APIRouter, Request

from deck_studio.server.api import ApiError, json_body

router = APIRouter()
LANGUAGES = {"en": "Inglês", "pt": "Português"}
NAMES = {"en": "English", "pt": "Brazilian Portuguese"}
TREE_KEYS = ("slidesDir", "studioBuild", "partBuild", "cleanBuild", "otherCleanBuilds", "jobs", "jobOutputs")


def _base_config(state):
    """The config keys a tree replaces, as the adapter gave them (kept before the first switch)."""
    return state.extras.setdefault("language-base", {k: copy.deepcopy(state.config.get(k)) for k in TREE_KEYS})


def _tree(state, lang):
    """The tree of `lang`, when the config names one and its slides folder exists in the kit."""
    tree = (state.config.get("languageTrees") or {}).get(lang)
    return tree if tree and (state.kit_root / tree["slidesDir"]).is_dir() else None


def _slides(state):
    """The base language's slides folder (where an i18n copy is shown)."""
    return state.kit_root / _base_config(state)["slidesDir"]


def _folder(state):
    return _slides(state).parent / "i18n"


def base(state):
    lang = state.config.get("language")
    return lang if lang in LANGUAGES else "en"


def active(state):
    lang = state.settings.get("language")
    if lang in LANGUAGES and _tree(state, lang):
        return lang
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
            "languages": [{"code": c, "label": label, "tree": bool(_tree(state, c)),
                           "available": c in (on, base(state)) or bool(_tree(state, c) or _html(_folder(state) / c))}
                          for c, label in LANGUAGES.items()]}


def _apply(state, lang):
    """Point the studio's config at `lang`: its tree's keys, or the base ones."""
    keys = copy.deepcopy(_base_config(state))
    tree = _tree(state, lang) or {}
    for k in TREE_KEYS:
        if k in ("jobs", "jobOutputs"):
            keys[k] = {**(keys[k] or {}), **tree.get(k, {})}
        elif k in tree:
            keys[k] = copy.deepcopy(tree[k])
    for k, v in keys.items():
        if v is None:
            state.config.pop(k, None)
        else:
            state.config[k] = v


def note(state):
    """A line for the agent's message when the slides on screen are not in the project's base language."""
    on = active(state)
    if on == base(state):
        return ""
    return (f"\n\n(Deck Studio: the slides in {state.config['slidesDir']} are now the {NAMES[on]} version of the deck. "
            f"Keep their text in {NAMES[on]}.)")


def translation_prompt(state, lang):
    """The chat message that asks the agent for the translation."""
    src = _base_config(state)["slidesDir"]
    out = f"{Path(src).parent.as_posix()}/i18n/{lang}"
    return (f"Traduza o deck para {LANGUAGES[lang].lower()} ({NAMES[lang]}). Para cada arquivo .html em {src}/, "
            f"escreva {out}/ com o mesmo nome e o mesmo HTML, só com o texto visível traduzido. Mantenha as tags, "
            "classes, ids, atributos data-*, componentes, fórmulas, números e nomes próprios como estão. "
            f"Não mude nada em {src}/. No fim, diga quantos arquivos traduziu.")


async def startup(state):
    """A tree language chosen before stays on screen after a restart."""
    _base_config(state)
    if active(state) != base(state) and _tree(state, active(state)):
        _apply(state, active(state))


@router.get("/api/language")
def get_language(request: Request):
    return payload(request.app.state.studio)


@router.get("/api/language/prompt/{lang}")
def get_prompt(lang: str, request: Request):
    if lang not in LANGUAGES:
        raise ApiError(400, "lang", "Idioma desconhecido.")
    return {"text": translation_prompt(request.app.state.studio, lang)}


def _swap_copies(state, on, lang):
    """The i18n layout: the base slides folder takes the copy of `lang`."""
    slides, keep, target = _slides(state), _folder(state) / on, _folder(state) / lang
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


@router.post("/api/language")
async def switch(request: Request):
    state = request.app.state.studio
    lang = (await json_body(request)).get("lang")
    if lang not in LANGUAGES:
        raise ApiError(400, "lang", "Idioma desconhecido.")
    on = active(state)
    if lang == on:
        return payload(state)
    tree = _tree(state, lang) or _tree(state, on)
    if not tree and lang != base(state) and not _html(_folder(state) / lang):
        raise ApiError(400, "missing", f"Ainda não há a versão em {LANGUAGES[lang].lower()}. Gere a tradução primeiro.")
    if state.turn_lock.locked():
        raise ApiError(409, "busy", "Espere o pedido em andamento terminar para trocar o idioma.")
    async with state.turn_lock:
        await state.publish_status()
        await state.builder.wait()  # no build of the other language still running
        if tree:
            state.settings["language"] = lang
            state.save_settings()
            _apply(state, lang)
        else:
            _swap_copies(state, on, lang)
    await state.publish_status()
    # a full build of the language now on screen, then the deck reloads
    await state.builder.sources_changed([str(state.kit_root / state.config["slidesDir"])])  # not a slide file
    return payload(state)
