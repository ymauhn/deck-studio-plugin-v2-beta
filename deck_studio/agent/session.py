"""Agent session: one chat = one long-lived SDK client (or the fake); each send() runs one turn.

A turn is one history turn and ends with exactly one turn-end, which carries the files it changed. The session's
hooks are the agent loop: PreToolUse decides every tool call with the write guard (an "ask" waits for the author)
and snapshots each file before its first write; PostToolUse rebuilds the deck after a write in its sources or a shell
command and hands a failed build back to the agent. SDK messages come out as chat events through `on_event` (an async callable taking
one dict): text, tool cards, errors (with the files changed so far) and the turn-end. Each finished turn also reports
the SDK session id ({"kind": "session"}), which a later ChatSession of the same chat resumes."""
import asyncio
import base64
import contextlib
import os
import re
from pathlib import Path

from claude_agent_sdk import (AssistantMessage, RateLimitEvent, ResultMessage, StreamEvent, SystemMessage, TextBlock,
                              ToolResultBlock, ToolUseBlock, UserMessage)

from deck_studio.agent.prompt import user_content
from deck_studio.agent.sdk import SHELL_TOOLS, make_client
from deck_studio.core.write_guard import DEFAULT_LEVEL, WRITE_TOOLS
from deck_studio.features import approvals
from deck_studio.render import Renderer

IMAGES = 4  # ponytail: images of a selection's first 4 slides; the agent takes screenshots of the others itself


def _decision(behavior, reason):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": behavior,
                                   "permissionDecisionReason": reason}}


def summary(name, tool_input, kit_root, whole=False):
    """A few words on a tool call for its card: the file (kit-relative), pattern, command or slide; never content.
    A tool card shows the first line, cut at 200 characters; an approval card (`whole`) shows every line and character,
    since the author allows all of it."""
    i = tool_input if isinstance(tool_input, dict) else {}
    if name in WRITE_TOOLS or name == "Read":
        path = i.get(WRITE_TOOLS.get(name, "file_path"))
        if not isinstance(path, str):
            return ""
        try:
            rel = os.path.relpath(os.path.join(kit_root, path), kit_root)
        except ValueError:  # another drive
            rel = ".."
        return (path if rel.startswith("..") else rel).replace("\\", "/")
    if name.startswith("mcp__deck__"):
        return " ".join(str(v) for k, v in i.items() if k in ("slide", "contextFile"))
    keys = {"Glob": "pattern", "Grep": "pattern", "Bash": "command", "PowerShell": "command", "WebFetch": "url",
            "WebSearch": "query", "Skill": "skill"}
    value = str(i.get(keys.get(name, ""), "")).strip()
    return value if whole else value.split("\n")[0][:200]


def _text(content):
    """The text of a tool result, without the CLI's <tool_use_error> tags."""
    if isinstance(content, list):
        content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    return re.sub(r"</?tool_use_error>", "", content or "").strip()


class ChatSession:
    def __init__(self, state, chat_id, model, on_event, resume=None, effort=""):
        self.state = state
        self.chat_id = chat_id
        self.model = model  # changes apply from the next turn on
        self.effort = effort  # "" is the model's default; a change reconnects on the next turn, resuming
        self._client_effort = effort
        self.resume = resume  # the SDK session id this chat continues, if any
        self.on_event = on_event
        self.closed = False
        self.client = None
        self.turn_id = None  # the running turn, for the hooks and the deck tools
        self._client_model = None
        self._task = None
        self._denied = {}  # tool_use_id -> the reason the PreToolUse hook denied it, for its card
        self._running = set()  # the tool calls of this turn still without a result

    def send(self, turn_id, text, selection=()):
        """Start one turn in the background. Every turn ends with a turn-end event, whatever happens."""
        self._task = asyncio.ensure_future(self._turn(turn_id, text, list(selection)))

    async def interrupt(self):
        """Stop the running turn (the Stop button); it ends with a message saying so. While the client is still
        connecting there is nothing to stop yet, and the call does nothing."""
        if self.turn_id and self.client:
            with contextlib.suppress(Exception):  # the SDK's "not connected"
                await self.client.interrupt()

    async def close(self):
        self.closed = True
        await self._disconnect()

    async def _disconnect(self):
        """Disconnect the client, if any; the next turn connects a new one."""
        if self.client:
            process = getattr(getattr(self.client, "_transport", None), "_process", None)  # the CLI's; the fake has none
            try:
                await self.client.disconnect()
            except Exception:  # noqa: BLE001 - the session is gone either way
                pass
            # The SDK never closes the CLI's stdout: after its reader stopped in the middle of a message, the pipe stays
            # open, and Python prints "I/O operation on closed pipe" on stderr when it collects it. Close it here.
            # ponytail: SDK 0.2.174 and anyio internals; drop this when the SDK's own close() closes stdout
            with contextlib.suppress(AttributeError):
                process._process._transport.close()
            self.client = None

    async def _turn(self, turn_id, text, selection):
        self.turn_id = turn_id
        try:
            self.state.history.begin(turn_id, {"chatId": self.chat_id, "text": text})
            if self.client is not None and self._client_effort != self.effort:  # effort is fixed at connect
                await self._disconnect()
            if self.client is None:
                await self._connect(turn_id)
            if self._client_model != self.model:
                await self.client.set_model(self.model)
                self._client_model = self.model
            await self.client.query(self._message(text, selection, await self._images(selection)))
            result = None
            async for m in self.client.receive_response():
                result = await self._handle(turn_id, m)
                if result is False:  # refused by the auth gate: nothing of this turn reaches the chat
                    return
            if result is None:
                await self._fail(turn_id, "A sessão do agente terminou. Envie a mensagem de novo para abrir outra.")
        except Exception as e:  # noqa: BLE001 - any agent failure ends the session with a message in the chat
            await self._fail(turn_id, "O agente parou com um erro inesperado. Envie a mensagem de novo para continuar.",
                             f"{type(e).__name__}: {e}")
        finally:
            self.turn_id = None
            for tool_id in self._running:  # its result never came: the card stops looking busy
                await self.on_event({"kind": "tool", "turnId": turn_id, "id": tool_id, "state": "stopped", "detail": ""})
            self._running.clear()
            if self.state.history.get(turn_id):
                self.state.history.end(turn_id)
            await self.on_event({"kind": "turn-end", "turnId": turn_id, "files": self._files(turn_id)})

    async def _connect(self, turn_id):
        """Connect a new client. When the chat's SDK session cannot be resumed (the CLI sweeps old transcripts), a
        new session takes over, and the chat says that the old context is gone."""
        self._client_effort = self.effort
        self.client = make_client(self.state, self.model, self)
        try:
            await self.client.connect()
        except Exception:
            if not self.resume:
                raise
            self.resume = None
            self.client = make_client(self.state, self.model, self)
            await self.client.connect()  # failing too, it is not the old session's fault: the chat keeps its id
            await self.on_event({"kind": "session", "sessionId": None})
            await self.on_event({"kind": "notice", "turnId": turn_id, "message":
                                 "O Claude Code não tem mais a sessão anterior deste chat (ele apaga as conversas "
                                 "antigas). Este pedido começou uma sessão nova, sem o contexto das mensagens acima."})
        self._client_model = self.model

    @staticmethod
    async def _message(text, selection, images):
        yield {"type": "user", "message": {"role": "user", "content": user_content(text, selection, images)},
               "parent_tool_use_id": None}

    async def _images(self, selection):
        """What the author saw when picking (SPEC story 15): an image of each slide and step of the selection, its
        boxes outlined, after its caption. TeX frames have none; a slide that cannot be shown gets a note instead."""
        views = {}  # (slide, step) -> the data-locs of its boxes
        for s in selection:
            loc, step = s.get("loc"), s.get("step")
            if isinstance(s.get("slide"), int) and isinstance(loc, dict):
                views.setdefault((s["slide"], step if isinstance(step, int) else None), []).append(
                    f"{loc.get('file')}:{loc.get('line')}:{loc.get('col')}")
        renderer = self.state.extras.setdefault("renderer", Renderer(self.state))
        blocks = []
        for (slide, step), locs in list(views.items())[:IMAGES]:
            try:
                png, label = await renderer.screenshot(slide, step, locs)
            except Exception as e:  # noqa: BLE001 - the message goes out without this image
                blocks.append({"type": "text", "text": f"(No image of slide {slide}: {e})"})
                continue
            blocks += [{"type": "text", "text": label}, {"type": "image", "source": {
                "type": "base64", "media_type": "image/png", "data": base64.b64encode(png).decode("ascii")}}]
        return blocks

    async def _handle(self, turn_id, m):
        """One SDK message: the ResultMessage that ends the turn, False when the auth gate refused, else None."""
        if isinstance(m, SystemMessage) and m.subtype == "init":
            refused = await self._refusal(m.data)
            await self.on_event({"kind": "auth", "ok": not refused})
            if refused:
                await self.close()
                await self.on_event({"kind": "error", "turnId": turn_id, "message": refused})
                return False
            # what this session really runs with
            await self.on_event({"kind": "init", "turnId": turn_id, "model": m.data.get("model"),
                                 "skills": m.data.get("skills", [])})
        elif isinstance(m, StreamEvent):
            e = m.event
            if e.get("type") == "content_block_delta" and e["delta"].get("type") == "text_delta":
                await self.on_event({"kind": "text-delta", "turnId": turn_id, "text": e["delta"]["text"]})
        elif isinstance(m, AssistantMessage):
            for block in m.content:
                if isinstance(block, TextBlock):
                    await self.on_event({"kind": "text", "turnId": turn_id, "text": block.text})
                elif isinstance(block, ToolUseBlock):
                    self._running.add(block.id)
                    await self.on_event({"kind": "tool", "turnId": turn_id, "id": block.id, "name": block.name,
                                         "summary": summary(block.name, block.input, self.state.kit_root),
                                         "state": "running"})
        elif isinstance(m, UserMessage) and isinstance(m.content, list):
            for block in m.content:
                if isinstance(block, ToolResultBlock):
                    self._running.discard(block.tool_use_id)
                    denied = self._denied.pop(block.tool_use_id, None)
                    state = "denied" if denied else "error" if block.is_error else "ok"
                    detail = denied or (_text(block.content)[:300] if block.is_error else "")
                    await self.on_event({"kind": "tool", "turnId": turn_id, "id": block.tool_use_id, "state": state,
                                         "detail": detail})
        elif isinstance(m, RateLimitEvent):
            # subscription windows (0..1); unifiedWindows is what the CLI sends, the typed fields are the fallback
            info = m.rate_limit_info
            windows = info.raw.get("unifiedWindows") or {info.rate_limit_type: {"utilization": info.utilization}}
            await self.on_event({"kind": "usage", **{k: (windows.get(k) or {}).get("utilization")
                                                     for k in ("five_hour", "seven_day")}})
        elif isinstance(m, ResultMessage):
            self.resume = m.session_id  # a reconnect (new effort) continues this conversation
            await self.on_event({"kind": "session", "sessionId": m.session_id})
            await self.on_event({"kind": "result", "turnId": turn_id, "subtype": m.subtype, "isError": m.is_error})
            if m.terminal_reason in ("aborted_streaming", "aborted_tools"):  # interrupt()
                await self._error(turn_id, "Pedido interrompido.")
            elif m.is_error:
                await self._error(turn_id, "O pedido terminou com um erro do Claude. Envie a mensagem de novo em "
                                           "alguns minutos.", m.result or "; ".join(m.errors or []) or m.subtype)
            return m
        return None

    async def _refusal(self, init):
        """Auth gate, checked on every init message: only the subscription login may answer."""
        source = init.get("apiKeySource")
        if source != "none":
            return (f"Chat recusado: ele usaria a chave de API ({source}) em vez da sua assinatura do Claude, "
                    "e esse uso é cobrado à parte.")
        account = (await self.client.get_server_info() or {}).get("account") or {}
        if not account.get("subscriptionType"):
            return ('Chat recusado: este login do Claude não tem uma assinatura. Entre de novo com '
                    '"claude auth login" num terminal e tente outra vez.')
        return None

    async def _fail(self, turn_id, message, detail=""):
        """End the session: the turn gets the error (its turn-end follows in _turn)."""
        await self.close()
        await self._error(turn_id, message, detail)

    async def _error(self, turn_id, message, detail=""):
        """The chat's error message, in Portuguese with what to do next, which says what the turn left changed in the
        files; the technical detail (the SDK's or the CLI's own words) goes below it, for whoever needs it."""
        files = self._files(turn_id)
        note = f"Ficaram alterados: {', '.join(files)}." if files else "Nenhum arquivo foi alterado."
        await self.on_event({"kind": "error", "turnId": turn_id, "message": f"{message} {note}",
                             **({"detail": detail} if detail else {})})

    def _files(self, turn_id):
        """The kit-relative files the turn has written so far."""
        turn = self.state.history.get(turn_id)
        return turn.files if turn else []

    # ---------- hooks: the SDK (or the fake) calls them during a turn ----------

    async def pre_tool_use(self, data, tool_use_id, context):
        """Every tool call is allowed or denied here, never left to the CLI; an error here denies it."""
        try:
            behavior, reason = await self._permission(data["tool_name"], data.get("tool_input") or {})
        except Exception as e:  # noqa: BLE001 - fail closed
            behavior, reason = "deny", f"Erro do estúdio ao checar esta chamada: {e}"
        if behavior != "allow":
            self._denied[tool_use_id] = reason
        return _decision(behavior, reason)

    async def _permission(self, name, tool_input):
        """(behavior, reason): the write guard decides and the author decides its asks; an allowed write gets its
        history snapshot first."""
        d = self.state.guard.check(name, tool_input, self.state.settings.get("autonomy", DEFAULT_LEVEL))
        behavior, reason = d.behavior, d.reason
        if behavior == "ask":
            answer = await approvals.ask(self.state, self.chat_id, self.turn_id, name,
                                         summary(name, tool_input, self.state.kit_root, whole=True), reason)
            behavior, reason = {"allow": ("allow", "Permitido pelo autor."),
                                "deny": ("deny", "Negado pelo autor.")}.get(
                answer, ("deny", "Negado: o autor não respondeu a tempo."))
        if behavior == "allow" and (path := self.state.guard.write_path(name, tool_input)):
            self.state.history.before_write(self.turn_id, path)
        return behavior, reason

    async def post_tool_use(self, data, tool_use_id, context):
        """After a write in the deck sources, or a shell command (which may have changed them): rebuild (the deck
        reloads when the build is good); a failed build goes back to the agent, so it fixes it in the same request."""
        sources = self.state.kit_root / Path(self.state.config["slidesDir"]).parent
        # ponytail: every approved command rebuilds; compare the sources' mtimes first if the reloads get in the way
        path = sources if data["tool_name"] in SHELL_TOOLS else self.state.guard.write_path(
            data["tool_name"], data.get("tool_input") or {})
        if not (path and Path(path).is_relative_to(sources)):
            return {}
        build = await self.state.builder.sources_changed([path])
        if build["ok"]:
            return {}
        return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext":
                f"The deck build failed after this edit. Fix it before you answer.\n\n{build['error']}"}}
