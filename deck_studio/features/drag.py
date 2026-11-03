"""Drag and resize on the deck's grid: POST /api/drag/apply writes a box's new layout to its source as one
undoable edit (ui/deck/drag.js measures and snaps it)."""
import re

from fastapi import APIRouter, Request

from deck_studio.core.source_edit import locate_element, set_attribute
from deck_studio.server.api import ApiError, json_body

router = APIRouter()
STYLE = {  # what a drag may write: the box's grid columns, its offset and its width
    "grid-column": re.compile(r"(1[0-3]|[1-9]) / (1[0-3]|[1-9])"),
    "translate": re.compile(r"(0|-?[1-9]\d{0,3}px) (0|-?[1-9]\d{0,3}px)"),
    "width": re.compile(r"[1-9]\d{0,3}px"),
}
CLASS = re.compile(r"-?[_a-zA-Z][\w-]*")


def merge_style(style, changes):
    """The style attribute with each property of changes set, or removed for None; other declarations stay as written."""
    out, left = [], dict(changes)
    for d in filter(str.strip, (style or "").split(";")):
        name, _, value = d.partition(":")
        prop = name.strip().lower()
        if prop not in left:
            out.append(d)
        elif (new := left.pop(prop)) is not None:
            out.append(f"{name}:{value[:len(value) - len(value.lstrip())]}{new}")  # its own spacing
    out += [f" {p}: {v}" for p, v in left.items() if v is not None]
    return ";".join(out).strip() or None


def merge_classes(classes, add, remove):
    """The class attribute without remove and with add at its end; the other classes keep their order."""
    names = [c for c in (classes or "").split() if c not in remove]
    return " ".join(names + [c for c in add if c not in names]) or None


def _names(v):
    return isinstance(v, list) and all(isinstance(c, str) and CLASS.fullmatch(c) for c in v)


@router.post("/api/drag/apply")
async def apply(request: Request):
    """{loc: {file, line, col}, tag, action?: "move" | "resize", classes?: {add, remove}, style?: {property: value | null}}:
    the box at loc gets that layout, through EditService (undoable; 409 while a turn runs)."""
    state = request.app.state.studio
    body = await json_body(request)
    loc = body.get("loc") if isinstance(body.get("loc"), dict) else {}
    file, line, col, tag = loc.get("file"), loc.get("line"), loc.get("col"), body.get("tag")
    style, classes = body.get("style", {}), body.get("classes", {})
    add, remove = (classes.get("add", []), classes.get("remove", [])) if isinstance(classes, dict) else (None, None)
    if not (isinstance(file, str) and type(line) is int and type(col) is int and isinstance(tag, str)
            and _names(add) and _names(remove) and isinstance(style, dict)
            and all(p in STYLE and (v is None or isinstance(v, str) and STYLE[p].fullmatch(v)) for p, v in style.items())):
        raise ApiError(400, "bad-drag", "Pedido de mudança de layout inválido.")

    def change(html):
        el = locate_element(html, line, col)
        if el is None:
            raise ApiError(409, "not-found", "Não achei essa caixa no arquivo. Recarregue e tente de novo.")
        if el.tag != tag:
            raise ApiError(409, "stale", "A caixa mudou no arquivo desde a seleção. Recarregue e tente de novo.")
        new = {"class": merge_classes(el.attrs.get("class"), add, remove) if add or remove else el.attrs.get("class"),
               "style": merge_style(el.attrs.get("style"), style) if style else el.attrs.get("style")}
        changed = [name for name, value in new.items() if value != el.attrs.get(name)]
        if not changed:
            raise ApiError(400, "no-change", "A caixa já está assim.")
        for name in changed:
            r = set_attribute(html, line, col, name, new[name])
            if not r.ok:  # generated: math, a table or inside a component
                raise ApiError(422, r.code, r.message)
            html = r.html
        return html

    what = "redimensionada" if body.get("action") == "resize" else "movida"
    return {"turnId": await state.edits.apply(f"Caixa {what} em {file.rsplit('/', 1)[-1]}:{line}", {file: change})}
