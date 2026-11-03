"""Direct edits and turns (SPEC stories 20, 21, 39-44): in-place text edits as undoable turns, and the diff
and undo of any turn, the agent's included."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from deck_studio.core.source_edit import replace_text
from deck_studio.edits import EditService
from deck_studio.server.api import ApiError, json_body

router = APIRouter()
# the source changed since the deck was built: 409; anything else replace_text refuses is not editable here: 422
CONFLICT = {"stale", "not-found"}


async def startup(state):
    state.edits = EditService(state)


@router.post("/api/edit-text")
async def edit_text(request: Request):
    """{loc: {file, line, col}, childIndex, oldText, newText}: one text node of the element at loc gets newText."""
    state = request.app.state.studio
    body = await json_body(request)
    loc = body.get("loc") if isinstance(body.get("loc"), dict) else {}
    file, line, col, index = loc.get("file"), loc.get("line"), loc.get("col"), body.get("childIndex")
    old, new = body.get("oldText"), body.get("newText")
    if not (isinstance(file, str) and all(type(v) is int for v in (line, col, index))
            and isinstance(old, str) and isinstance(new, str)):
        raise ApiError(400, "bad-edit", "Pedido de edição incompleto.")
    if not new.strip():  # an empty box could not be double-clicked again
        raise ApiError(400, "empty", "O texto não pode ficar vazio. Para tirar a caixa, peça no chat.")

    def change(html):
        r = replace_text(html, line, col, index, old, new)
        if not r.ok:
            raise ApiError(409 if r.code in CONFLICT else 422, r.code, r.message)
        return r.html

    return {"turnId": await state.edits.apply(f"Texto editado em {file.rsplit('/', 1)[-1]}:{line}", {file: change})}


def known(state, turn_id):
    if state.history.get(turn_id) is None:
        raise ApiError(404, "no-turn", "Pedido não encontrado no histórico.")


@router.get("/api/turns")
async def turns(request: Request):
    """The turns that changed files, oldest first, for their cards after a page reload: direct edits are drawn from
    this list, agent turns come back with their chat and take only their undone state from it."""
    return [{"turnId": t.id, "kind": "edit" if (t.meta or {}).get("kind") == "edit" else "agent",
             "label": (t.meta or {}).get("label"), "files": t.files, "undone": t.undone}
            for t in request.app.state.studio.history.list() if t.ended and t.files]


@router.get("/api/turns/{turn_id}/diff")
async def turn_diff(turn_id: str, request: Request):  # async: history is used from the event loop only
    state = request.app.state.studio
    known(state, turn_id)
    return {"diff": state.history.diff(turn_id)}


@router.post("/api/turns/{turn_id}/undo")
async def turn_undo(turn_id: str, request: Request):
    state = request.app.state.studio
    known(state, turn_id)
    r = await state.edits.undo(turn_id)
    if not r.ok:
        message = (f"Não dá para desfazer: {', '.join(r.conflicts)} {'mudou' if len(r.conflicts) == 1 else 'mudaram'} "
                   "depois deste pedido. Desfaça antes as mudanças mais novas.")
        return JSONResponse({"error": "conflict", "message": message, "conflicts": r.conflicts}, 409)
    return {"restored": r.restored, "removed": r.removed}
