"""The deck tools: the in-process MCP server "deck" each chat session gives its agent (SPEC "Deep modules" 6)."""
import asyncio
import base64
import json
import os
import re
import unicodedata
from pathlib import Path

from claude_agent_sdk import create_sdk_mcp_server, tool

from deck_studio.beamer import engine
from deck_studio.features import beamer
from deck_studio.render import Renderer

IMAGE_TYPES = {".png": ".png", ".jpg": ".jpg", ".jpeg": ".jpg", ".webp": ".webp", ".svg": ".svg"}  # the build's types
SLIDE = {"slide": {"type": "integer", "minimum": 1, "description": "Slide number, 1-based (a selection's slide)"},
         "step": {"type": "integer", "minimum": 0,
                  "description": "Fragment step; leave it out for the last step, with everything shown"}}
DECK = {"path": {"type": "string", "description": "The deck's main .tex, kit-relative; by default the project's "
                                                  "Beamer deck"}}


def _text(text, error=False):
    return {"content": [{"type": "text", "text": text}], "is_error": error}


def safe_name(name):
    """Lowercase ASCII letters, digits and hyphens: "Gráfico Final" is "grafico-final"."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-") or "imagem"


def deck_server(state, session):
    """The tools of one chat session. The renderer (one headless page) is shared by every session."""
    renderer = state.extras.setdefault("renderer", Renderer(state))

    async def rendering(job):
        """A renderer job's result, or an error result the agent can read."""
        try:
            return await job
        except FileNotFoundError:
            return _text("The studio deck has not been built yet: call rebuild_deck.", error=True)
        except ValueError as e:
            return _text(str(e), error=True)

    @tool("get_selection", "The boxes the author selected on the slides for this request, as JSON "
          "(slide, step, source loc, tag, text, kind; maybe a comment or a TeX frame).", {})
    async def get_selection(args):
        return _text(json.dumps(state.selection, ensure_ascii=False))

    @tool("rebuild_deck", "Build the studio deck now and report its errors. Edits to the deck sources already "
          "rebuild it; use this after other changes or to see the errors again.", {})
    async def rebuild_deck(args):
        build = await state.builder.build_studio()
        if not build["ok"]:
            return _text(f"The studio deck build failed:\n{build['error']}", error=True)
        await state.events.publish("deck-reload")
        return _text(f"The studio deck built without errors in {build['ms']} ms.")

    @tool("screenshot_slide", "A PNG of a slide as the audience sees it (1600x900). Look at it after every edit "
          "and fix overflow or overlap before you answer.",
          {"type": "object", "properties": {**SLIDE, "highlightLoc": {
              "type": "string", "description": "A data-loc (file:line:col) whose element gets an orange outline"}},
           "required": ["slide"]})
    async def screenshot_slide(args):
        async def job():
            png, label = await renderer.screenshot(args["slide"], args.get("step"),
                                                   [loc] if (loc := args.get("highlightLoc")) else [])
            return {"content": [{"type": "text", "text": label},
                                {"type": "image", "data": base64.b64encode(png).decode("ascii"),
                                 "mimeType": "image/png"}]}
        return await rendering(job())

    @tool("check_slide", "Check a slide for boxes that clip their content and elements outside the 1600x900 "
          "frame; each problem names its element and data-loc.",
          {"type": "object", "properties": SLIDE, "required": ["slide"]})
    async def check_slide(args):
        async def job():
            problems, label = await renderer.check(args["slide"], args.get("step"))
            if not problems:
                return _text(f"{label[:-1]}: nothing clipped and nothing outside the 1600x900 frame.")
            return _text(f"{label[:-1]}: {len(problems)} problem{'s' * (len(problems) > 1)}.\n"
                         + "\n".join(f"- {p}" for p in problems))
        return await rendering(job())

    @tool("add_image", "Copy an image the author dropped in the context folder into the deck's images, under a new "
          "safe name, and get the <img> tag that puts it on a slide.",
          {"type": "object", "properties": {
              "contextFile": {"type": "string", "description": "The image's path inside the context folder"},
              "name": {"type": "string", "description": "A name for the copy; by default the file's own name"}},
           "required": ["contextFile"]})
    async def add_image(args):
        context = state.kit_root / state.config["contextDir"]
        source = (context / args["contextFile"]).resolve()
        if not (source.is_relative_to(context.resolve()) and source.is_file()):
            return _text(f"The image must be a file in the context folder; {args['contextFile']} is not.", error=True)
        ext = IMAGE_TYPES.get(source.suffix.lower())
        if not ext:
            return _text(f"Only png, jpg, webp or svg images can go on a slide; {source.name} is not one.", error=True)
        images = state.kit_root / state.config["imagesDir"]
        stem = safe_name(Path(args.get("name") or source.name).stem)
        target, n = images / f"{stem}{ext}", 1
        while target.exists():  # never overwrite
            n += 1
            target = images / f"{stem}-{n}{ext}"
        state.history.before_write(session.turn_id, target)
        images.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        src = Path(os.path.relpath(target, state.kit_root / Path(state.config["slidesDir"]).parent)).as_posix()
        return _text(f"Copied to {target.relative_to(state.kit_root).as_posix()}. Put it on a slide with "
                     f'<img src="{src}" alt="..."> and a real alt text.')

    @tool("compile_beamer", "Compile a hand-written Beamer deck with latexmk, as the studio's Beamer view does: the "
          "author's screen shows it too. Answers JSON {ok, pages, errors: [{file, line, message}], boxes: [{file, "
          "line, message}]}: boxes are the overfull boxes over 1 pt, with their size (a frame too tall runs into the "
          "footline, a line too wide into the margin): fix those as you fix errors. The underfull ones listed there "
          "are only hints: change them only when the page looks wrong. TeX reports "
          "an error or a box inside a frame on that frame's \\end{frame} line. TeX reads only files inside the deck's "
          "folder: copy a figure there before you include it.",
          {"type": "object", "properties": DECK})
    async def compile_beamer(args):
        try:
            deck = beamer.deck_for(state, args.get("path"))
        except ValueError as e:
            return _text(str(e), error=True)
        result = await asyncio.shield(deck.full())  # shared with the view: a cancelled call leaves it running
        return _text(json.dumps(result, ensure_ascii=False), error=not result["ok"])

    @tool("screenshot_beamer_page", "A PNG of a page of a hand-written Beamer deck as its last compile made it, "
          "1600 px wide. Look at it after compile_beamer; fix overfull, clipped or crowded content before you answer.",
          {"type": "object", "properties": {
              "page": {"type": "integer", "minimum": 1, "description": "Page number, 1-based"}, **DECK},
           "required": ["page"]})
    async def screenshot_beamer_page(args):
        try:
            deck = beamer.deck_for(state, args.get("path"))
        except ValueError as e:
            return _text(str(e), error=True)
        view, n = deck.current(), args["page"]
        if not view:
            return _text(f"{deck.rel} has not been compiled yet: call compile_beamer.", error=True)
        if n > view["pages"]:
            return _text(f"{deck.rel} has {view['pages']} pages in its last compile.", error=True)
        png = await asyncio.to_thread(engine.render_page, view["pdf"], n, round(1600 * 72 / view["width"]))
        return {"content": [{"type": "text", "text": f"Page {n} of {view['pages']} of {deck.rel}."},
                            {"type": "image", "data": base64.b64encode(png).decode("ascii"), "mimeType": "image/png"}]}

    return create_sdk_mcp_server("deck", tools=[get_selection, rebuild_deck, screenshot_slide, check_slide, add_image,
                                                compile_beamer, screenshot_beamer_page])
