"""Comment batches: the author's comments on boxes across slides, kept in data_dir/comments.json.

A comment is {id, text, selection, sent}: `selection` is the list of boxes it was made on (SPEC Selection items) and
`sent` the turn it went out with, or None. Every change publishes `comments` with the whole list, sorted by slide.
The UI applies a batch as one chat message whose selection items carry `comment` and `commentId`."""
import asyncio
import json
import uuid

from fastapi import APIRouter, Request

from deck_studio.server.api import ApiError, json_body

router = APIRouter()


class Comments:
    def __init__(self, state):
        self.state = state
        self.file = state.data_dir / "comments.json"
        try:
            self.items = json.loads(self.file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.items = []
        for c in self.items:
            c["sent"] = None  # no turn outlives the studio

    def public(self):
        return sorted(self.items, key=lambda c: min(s["slide"] for s in c["selection"]))  # stable: then by age

    def get(self, comment_id):
        comment = next((c for c in self.items if c["id"] == comment_id), None)
        if not comment:
            raise ApiError(404, "not-found", "Comentário não encontrado.")
        return comment

    async def save(self):
        self.file.write_text(json.dumps(self.items, ensure_ascii=False, indent=2), encoding="utf-8")
        await self.state.events.publish("comments", comments=self.public())


async def startup(state):
    store = state.extras["comments"] = Comments(state)
    store.watcher = asyncio.ensure_future(watch(store, state.events))


async def watch(store, events):
    """The turn whose message carries a comment's id marks it sent; that turn's end clears it, or, after an error
    or a stop, unmarks it so it can be applied again."""
    failed = set()
    async for e in events.stream():
        kind, turn = e.get("kind"), e.get("turnId")
        if e["type"] != "chat" or not turn:
            continue
        if kind == "user":
            ids = {s.get("commentId") for s in e.get("selection") or []}
            batch = [c for c in store.items if c["id"] in ids and not c["sent"]]
            for c in batch:
                c["sent"] = turn
        elif kind == "error" or (kind == "result" and e.get("isError")):  # an interrupt is an error too
            failed.add(turn)
            continue
        elif kind == "turn-end":
            batch = [c for c in store.items if c["sent"] == turn]
            if turn in failed:
                for c in batch:
                    c["sent"] = None
            else:
                store.items = [c for c in store.items if c["sent"] != turn]
            failed.discard(turn)
        else:
            continue
        if batch:
            await store.save()


def store_of(request):
    return request.app.state.studio.extras["comments"]


def text_of(body):
    text = body.get("text").strip() if isinstance(body.get("text"), str) else ""
    if not text:
        raise ApiError(400, "empty", "Escreva o comentário.")
    return text


@router.get("/api/comments")
def list_comments(request: Request):
    return store_of(request).public()


@router.post("/api/comments", status_code=201)
async def add_comment(request: Request):
    store = store_of(request)
    body = await json_body(request)
    selection = body.get("selection")
    if not (isinstance(selection, list) and selection
            and all(isinstance(s, dict) and isinstance(s.get("slide"), int) for s in selection)):
        raise ApiError(400, "selection", "Selecione uma ou mais caixas do deck para comentar.")
    comment = {"id": uuid.uuid4().hex[:8], "text": text_of(body), "selection": selection[:50], "sent": None}
    store.items.append(comment)
    await store.save()
    return comment


@router.patch("/api/comments/{comment_id}")
async def edit_comment(comment_id: str, request: Request):
    text = text_of(await json_body(request))
    store = store_of(request)
    comment = store.get(comment_id)
    comment["text"] = text
    await store.save()
    return comment


@router.delete("/api/comments/{comment_id}", status_code=204)
async def delete_comment(comment_id: str, request: Request):
    store = store_of(request)
    store.items.remove(store.get(comment_id))
    await store.save()
