"""Chat routes: chats in tabs, each with its own agent session, title and model; one turn at a time across all chats.

A chat lives in data_dir/chats/<id>.json: its title, model, SDK session id and the `chat` events that redraw its
conversation (user, text, error, tool, and a turn-end with files), numbered by `seq`. The chats are loaded again at
startup, and a chat's next session resumes its SDK session by id."""
import json
import os
import re
import sys
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from fastapi import APIRouter, Request

from deck_studio.agent.session import ChatSession
from deck_studio.server.api import ApiError, json_body

MODELS = ["opus", "sonnet", "haiku"]  # Claude Code model aliases; Opus for new chats
# reasoning effort levels of the Agent SDK (EffortLevel); "" is the model's own default
EFFORTS = ["", "low", "medium", "high", "xhigh", "max"]
# the chat events a conversation is redrawn from (plus turn-ends with files)
KEPT = {"user", "text", "error", "notice", "tool"}


@dataclass
class Chat:
    id: str
    title: str
    model: str
    effort: str = ""
    session_id: str | None = None  # the SDK session this chat continues
    messages: list = field(default_factory=list)  # the kept chat events
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)  # when the last kept event came
    restored: bool = False  # loaded from disk at startup
    turn: str | None = None  # the running turn
    session: ChatSession | None = None

    def public(self):
        return {"id": self.id, "title": self.title, "model": self.model, "effort": self.effort, "running": bool(self.turn),
                "restored": self.restored, "updated": self.updated, "messages": self.messages}

    def saved(self):
        return {"id": self.id, "title": self.title, "model": self.model, "effort": self.effort, "sessionId": self.session_id,
                "created": self.created, "updated": self.updated, "messages": self.messages}


def folder(state):
    return state.data_dir / "chats"


def save(state, chat):
    """Write the chat's file whole; the replace is atomic, so a killed studio leaves the last good copy. A failed
    write (say, a file another program holds) leaves the chat running: the next change writes it all again."""
    # ponytail: the whole file per kept event; an append-only log if chats grow to many MB
    try:
        folder(state).mkdir(exist_ok=True)
        temp = folder(state) / f"{chat.id}.tmp"
        temp.write_text(json.dumps(chat.saved(), ensure_ascii=False), encoding="utf-8")
        os.replace(temp, folder(state) / f"{chat.id}.json")
    except OSError as e:
        print(f"Deck Studio: o chat {chat.id} não foi salvo: {e}", file=sys.stderr)


@asynccontextmanager
async def lifespan(app):
    """The saved chats come back at startup, in the order they were opened; a file that does not load is skipped."""
    state = app.state.studio
    loaded = []
    for file in folder(state).glob("*.json"):
        try:
            d = json.loads(file.read_text(encoding="utf-8"))
            loaded.append(Chat(file.stem, d["title"], d["model"], d.get("effort") or "", d.get("sessionId"),
                               d["messages"], d["created"], d["updated"], restored=True))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    for chat in sorted(loaded, key=lambda c: c.created):
        state.chats[chat.id] = chat
    yield


router = APIRouter(lifespan=lifespan)


def next_title(chats):
    """"Chat <n>", one past the highest number in use."""
    numbers = [int(m[1]) for c in chats.values() if (m := re.fullmatch(r"Chat (\d+)", c.title))]
    return f"Chat {max(numbers, default=0) + 1}"


def chat_of(request, chat_id):
    chat = request.app.state.studio.chats.get(chat_id)
    if not chat:
        raise ApiError(404, "not-found", "Chat não encontrado.")
    return chat


async def record(state, chat, e):
    """Publish one `chat` event of this chat; the ones that redraw its conversation are kept, numbered by seq."""
    e = {"chatId": chat.id, **e}
    if e["kind"] in KEPT or (e["kind"] == "turn-end" and e.get("files")):
        chat.messages.append(e)
        e["seq"] = len(chat.messages)
        chat.updated = time.time()
        save(state, chat)
    await state.events.publish("chat", **e)


async def on_session_event(state, chat, e):
    """Session events become status changes, the chat's SDK session id or `chat` events; a turn-end frees the turn
    lock."""
    if e["kind"] == "usage":
        state.usage.update({k: v for k, v in e.items() if k in state.usage and isinstance(v, (int, float))})
        return await state.publish_status()
    if e["kind"] == "auth":
        state.auth = "ok" if e["ok"] else "refused"
        return await state.publish_status()
    if e["kind"] == "session":
        chat.session_id = e["sessionId"]
        return save(state, chat)
    await record(state, chat, e)
    if e["kind"] == "turn-end":
        chat.turn = None
        if state.turn_lock.locked():
            state.turn_lock.release()
            await state.publish_status()


@router.get("/api/chats")
def list_chats(request: Request):
    return [c.public() for c in request.app.state.studio.chats.values()]


@router.post("/api/chats", status_code=201)
async def new_chat(request: Request):
    """A new chat ({model?, effort?}); without them it takes the settings' model and effort of new chats."""
    state = request.app.state.studio
    body = await json_body(request)
    model, effort = body.get("model"), body.get("effort")
    if model not in MODELS:
        model = state.settings.get("model", MODELS[0])
    if effort not in EFFORTS:
        effort = state.settings.get("effort", "")
    chat = Chat(str(uuid.uuid4()), next_title(state.chats), model, effort)
    state.chats[chat.id] = chat
    save(state, chat)
    return chat.public()


@router.post("/api/chats/{chat_id}/messages", status_code=202)
async def send_message(chat_id: str, request: Request):
    state = request.app.state.studio
    chat = chat_of(request, chat_id)
    body = await json_body(request)
    text = body["text"].strip() if isinstance(body.get("text"), str) else ""
    if not text:
        raise ApiError(400, "empty", "Escreva uma mensagem.")
    selection = body.get("selection") if isinstance(body.get("selection"), list) else []
    selection = [s for s in selection if isinstance(s, dict)][:50]
    if state.turn_lock.locked():
        raise ApiError(409, "busy", "Outro pedido está em andamento.")
    await state.turn_lock.acquire()  # released by this turn's turn-end, which every session path emits
    if chat.session is None or chat.session.closed:  # a refused or ended session is replaced, resuming the chat's
        chat.session = ChatSession(state, chat.id, chat.model, lambda e: on_session_event(state, chat, e),
                                   resume=chat.session_id, effort=chat.effort)
    turn_id = chat.turn = str(uuid.uuid4())
    state.selection = selection
    await state.publish_status()
    await record(state, chat, {"kind": "user", "turnId": turn_id, "text": text, "selection": selection})
    chat.session.send(turn_id, text, selection)
    return {"turnId": turn_id}


@router.post("/api/chats/{chat_id}/interrupt")
async def interrupt(chat_id: str, request: Request):
    """Stop the chat's running turn; the turn ends with a message saying so."""
    chat = chat_of(request, chat_id)
    if chat.session:
        await chat.session.interrupt()
    return chat.public()


@router.post("/api/chats/{chat_id}/model")
async def set_model(chat_id: str, request: Request):
    chat = chat_of(request, chat_id)
    model = (await json_body(request)).get("model")
    if model not in MODELS:
        raise ApiError(400, "model", "Modelo desconhecido.")
    chat.model = model
    if chat.session:
        chat.session.model = model
    save(request.app.state.studio, chat)
    return chat.public()


@router.post("/api/chats/{chat_id}/effort")
async def set_effort(chat_id: str, request: Request):
    """The chat's reasoning effort; the agent reconnects with it on the next turn, in the same conversation."""
    chat = chat_of(request, chat_id)
    effort = (await json_body(request)).get("effort")
    if effort not in EFFORTS:
        raise ApiError(400, "effort", "Nível de esforço desconhecido.")
    chat.effort = effort
    if chat.session:
        chat.session.effort = effort
    save(request.app.state.studio, chat)
    return chat.public()


@router.post("/api/chats/{chat_id}/title")
async def set_title(chat_id: str, request: Request):
    chat = chat_of(request, chat_id)
    title = (await json_body(request)).get("title")
    title = title.strip()[:60] if isinstance(title, str) else ""
    if not title:
        raise ApiError(400, "title", "Dê um nome ao chat.")
    chat.title = title
    save(request.app.state.studio, chat)
    return chat.public()


@router.delete("/api/chats/{chat_id}")
async def close_chat(chat_id: str, request: Request):
    """Close a tab: the chat, its file and its session go; a chat with a running turn is kept."""
    state = request.app.state.studio
    chat = chat_of(request, chat_id)
    if chat.turn:
        raise ApiError(409, "busy", "Pare o pedido deste chat antes de fechá-lo.")
    del state.chats[chat.id]
    (folder(state) / f"{chat.id}.json").unlink(missing_ok=True)
    if chat.session:
        await chat.session.close()
    return {"id": chat.id}
