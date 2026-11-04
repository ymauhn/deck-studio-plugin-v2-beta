"""Scripted stand-in for ClaudeSDKClient in tests: the same methods, the SDK's own message types.

Each user message picks <scenarios>/<name>.json with the marker #scenario:<name>; without one the fake says "ok".
A scenario is {"init"?: {...}, "steps": [...]}. Steps:
- {"say": text}: text deltas and the assistant message; {{model}}, {{effort}}, {{message}} (the user message's text), {{session}} (the session id: options.resume when
  resuming), {{selection}}, {{selection_raw}}, {{images}} (the message's images with their captions), {{result}}
  (the text of the last tool result), {{context}} (what that call's PostToolUse hooks added) and {{appendix}} (what
  the system prompt adds to the Claude Code preset) are filled in;
- {"tool": name, "input": {...}}: a tool call as the CLI makes it, through the options' real PreToolUse and
  PostToolUse hooks; Edit, Write and Read act on the files (relative paths are in the kit), other tools are only
  simulated, never run; {"approval": name, "input": {...}} is the same, for a call the guard asks about;
- {"mcp": deck tool name, "input": {...}}: a deck tool call, through the hooks and the in-process MCP server;
- "crash": text on a tool step: the SDK fails during that call, after its tool_use and before its result, as its
  reader does on a message over its buffer (CLIJSONDecodeError);
- {"fail": text}: the turn ends with an error result, as when the API fails;
- {"rate": {"five_hour": 0..1, "seven_day": 0..1}} or {"wait": ms}.
"init" overrides apiKeySource and subscriptionType of that turn's init message and account. interrupt() ends the
running turn as the CLI does: a waiting step or hook call is cancelled and an aborted error result follows.
A session id that starts with "gone-" plays one the CLI no longer has (its transcript was swept): resuming it fails
at connect(), as the CLI refuses the resume."""
import asyncio
import base64
import json
import math
import re
import time
import uuid
from pathlib import Path

from claude_agent_sdk import (AssistantMessage, CLIJSONDecodeError, RateLimitEvent, RateLimitInfo, ResultError,
                              ResultMessage, StreamEvent, SystemMessage, TextBlock, ToolResultBlock, ToolUseBlock,
                              UserMessage)
from mcp import Client  # the SDK's own MCP dependency: deck tools are called the way the CLI calls them

USAGE = {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}


def text_of(content):
    return content if isinstance(content, str) else "\n".join(b["text"] for b in content if b.get("type") == "text")


def raw_selection(text):
    """{{selection_raw}}: the JSON of the <selection> block the session sent, as sent ("" without one)."""
    m = re.search(r"<selection>\n(.*)\n</selection>", text, re.S)
    return m[1] if m else ""


def selection_of(text):
    """{{selection}}: one "slide tag part:line" (a TeX frame: "tex file:line") per box of the <selection> block."""
    boxes = json.loads(raw_selection(text) or "[]")
    return ", ".join(f"tex {s['file']}:{s['line']}" if s.get("kind") == "tex"
                     else f"{s['slideId']} {s['tag']} {s['part']}:{s['loc']['line']}" for s in boxes) or "nenhuma"


def images_of(content):
    """{{images}}: each image the user message carries, after its caption (the text block just before it)."""
    blocks = [] if isinstance(content, str) else content
    return "\n".join(shown(blocks[max(i - 1, 0):i + 1]) for i, b in enumerate(blocks)
                     if b.get("type") == "image") or "nenhuma"


def pieces(text):
    """About three text deltas per answer."""
    n = max(1, math.ceil(len(text) / 3))
    return [text[i:i + n] for i in range(0, len(text), n)] or [""]


def shown(result):
    """{{result}}: a tool result's text; an image shows as [<type> <width>x<height>] (PNG sizes are read)."""
    if isinstance(result, str):
        return result
    out = []
    for b in result:
        if b["type"] == "text":
            out.append(b["text"])
        else:
            png = base64.b64decode(b["source"]["data"])
            size = f" {int.from_bytes(png[16:20])}x{int.from_bytes(png[20:24])}" if png[1:4] == b"PNG" else ""
            out.append(f"[{b['source']['media_type']}{size}]")
    return "\n".join(out)


class Interrupted(Exception):
    pass


class FakeClient:
    def __init__(self, scenarios_dir, options):
        self.scenarios = Path(scenarios_dir)
        self.options = options
        self.model = options.model
        self.session_id = options.resume or str(uuid.uuid4())  # a resumed session keeps its id, as in the CLI
        self._prompts = asyncio.Queue()
        self._account = None  # what get_server_info() reports, from the current turn's scenario
        self._result = ""  # {{result}}
        self._context = ""  # {{context}}: what the last tool call's PostToolUse hooks added for the agent
        self._stop = asyncio.Event()  # set by interrupt(), cleared when the turn has ended

    async def connect(self, prompt=None):
        if (self.options.resume or "").startswith("gone-"):  # the CLI's own words, through the SDK
            raise ResultError("Claude Code returned an error result: No conversation found with session ID: "
                              f"{self.options.resume}", exit_code=1)

    async def disconnect(self):
        pass

    async def interrupt(self):
        self._stop.set()

    async def set_model(self, model=None):
        self.model = model

    async def get_server_info(self):
        return {"account": self._account, "models": [], "commands": [], "output_style": "default"}

    async def query(self, prompt, session_id="default"):
        if isinstance(prompt, str):
            self._prompts.put_nowait(prompt)
        else:
            async for message in prompt:
                self._prompts.put_nowait(message["message"]["content"])

    async def receive_response(self):
        """One turn: the init message, the scenario's steps, the result."""
        t0 = time.monotonic()
        content = await self._prompts.get()
        text = text_of(content)
        name = re.search(r"#scenario:([\w-]+)", text)
        scenario = json.loads((self.scenarios / f"{name[1]}.json").read_text(encoding="utf-8")) if name else {
            "steps": [{"say": "ok"}]}
        init = {"apiKeySource": "none", "subscriptionType": "max", **scenario.get("init", {})}
        self._account = {"subscriptionType": init["subscriptionType"], "apiProvider": "firstParty"}
        # the CLI announces itself at the start of every turn
        yield SystemMessage("init", {
            "type": "system", "subtype": "init", "apiKeySource": init["apiKeySource"], "claude_code_version": "fake",
            "cwd": str(self.options.cwd), "tools": [], "mcp_servers": [], "model": self.model,
            "permissionMode": self.options.permission_mode or "default", "slash_commands": [], "output_style": "default",
            "skills": list(self.options.skills or []), "plugins": [], **self._meta()})
        values = {"model": lambda: str(self.model), "effort": lambda: str(self.options.effort or "padrão"), "message": lambda: text, "session": lambda: self.session_id,
                  "selection": lambda: selection_of(text),
                  "selection_raw": lambda: raw_selection(text), "images": lambda: images_of(content),
                  "result": lambda: self._result, "context": lambda: self._context,
                  "appendix": lambda: (self.options.system_prompt or {}).get("append", "")}
        last = ""
        try:
            for step in scenario["steps"]:
                if self._stop.is_set():
                    raise Interrupted
                if "say" in step:
                    last = re.sub(r"\{\{(\w+)\}\}", lambda m: values[m[1]]() if m[1] in values else m[0], step["say"])
                    for message in self._say(last):
                        yield message
                elif {"tool", "approval", "mcp"} & step.keys():
                    name = f"mcp__deck__{step['mcp']}" if "mcp" in step else step.get("tool") or step["approval"]
                    async for message in self._tool(name, step.get("input", {}), step.get("crash")):
                        yield message
                elif "fail" in step:
                    yield self._end(t0, "error_during_execution", step["fail"], errors=[step["fail"]])
                    return
                elif "rate" in step:
                    yield self._rate(step["rate"])
                elif "wait" in step:
                    await self._unless_stopped(asyncio.sleep(step["wait"] / 1000))
                else:
                    raise ValueError(f"fake agent: unknown step {json.dumps(step)}")
            yield self._end(t0, "success", last)
        except Interrupted:
            yield UserMessage(content=[TextBlock("[Request interrupted by user]")], uuid=str(uuid.uuid4()))
            yield self._end(t0, "error_during_execution", "", terminal_reason="aborted_streaming")
        finally:
            self._stop.clear()

    def _end(self, t0, subtype, result, **more):
        """The turn's ResultMessage."""
        return ResultMessage(
            subtype=subtype, duration_ms=round((time.monotonic() - t0) * 1000), duration_api_ms=0,
            is_error=subtype != "success", num_turns=1, session_id=self.session_id,
            stop_reason="end_turn" if subtype == "success" else None, total_cost_usd=0, usage=USAGE, result=result,
            model_usage={}, permission_denials=[], uuid=str(uuid.uuid4()),
            **{"terminal_reason": "completed", **more})

    async def _unless_stopped(self, awaitable):
        """Await it, unless interrupt() comes first: then it is cancelled (as the CLI cancels a hook call)."""
        task, stop = asyncio.ensure_future(awaitable), asyncio.ensure_future(self._stop.wait())
        await asyncio.wait({task, stop}, return_when=asyncio.FIRST_COMPLETED)
        stop.cancel()
        if not task.done():
            task.cancel()
            raise Interrupted
        return task.result()

    def _meta(self):
        return {"uuid": str(uuid.uuid4()), "session_id": self.session_id}

    def _stream(self, event):
        return StreamEvent(event=event, parent_tool_use_id=None, **self._meta())

    def _assistant(self, block, start, deltas, stop_reason):
        """One assistant message with one content block, between its stream events (only with partial messages,
        as in the SDK)."""
        message_id = f"msg_{uuid.uuid4()}"
        partial = self.options.include_partial_messages
        if partial:
            yield self._stream({"type": "message_start", "message": {
                "id": message_id, "type": "message", "role": "assistant", "model": self.model, "content": [],
                "stop_reason": None, "stop_sequence": None, "usage": USAGE}})
            yield self._stream({"type": "content_block_start", "index": 0, "content_block": start})
            for delta in deltas:
                yield self._stream({"type": "content_block_delta", "index": 0, "delta": delta})
        yield AssistantMessage(content=[block], model=self.model, usage=USAGE, message_id=message_id,
                               session_id=self.session_id, uuid=str(uuid.uuid4()))
        if partial:
            yield self._stream({"type": "content_block_stop", "index": 0})
            yield self._stream({"type": "message_delta", "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                                "usage": USAGE})
            yield self._stream({"type": "message_stop"})

    def _say(self, text):
        return self._assistant(TextBlock(text), {"type": "text", "text": ""},
                               [{"type": "text_delta", "text": p} for p in pieces(text)], "end_turn")

    async def _tool(self, name, tool_input, crash=None):
        """The assistant's tool_use, the PreToolUse hooks, the tool, the PostToolUse hooks, then the tool_result;
        with `crash`, the SDK fails right after the tool_use."""
        tool_use_id = f"toolu_{uuid.uuid4().hex[:24]}"
        for message in self._assistant(ToolUseBlock(tool_use_id, name, tool_input),
                                       {"type": "tool_use", "id": tool_use_id, "name": name, "input": {}},
                                       [{"type": "input_json_delta", "partial_json": json.dumps(tool_input)}],
                                       "tool_use"):
            yield message
        if crash:
            raise CLIJSONDecodeError(crash, ValueError(crash))
        call = {"tool_name": name, "tool_input": tool_input, "tool_use_id": tool_use_id}
        decisions = await self._unless_stopped(self._hooks("PreToolUse", call))
        denial = next((o for o in decisions if o.get("permissionDecision") == "deny"), None)
        self._context = ""
        if denial:  # worded as the CLI words it
            result, error = f"PreToolUse:{name} hook error: {denial.get('permissionDecisionReason', '')}", True
        else:
            result, error = await self._run(name, tool_input)
            if not error:
                outputs = await self._hooks("PostToolUse", {**call, "tool_response": result})
                self._context = "\n".join(o["additionalContext"] for o in outputs if o.get("additionalContext"))
        self._result = shown(result)
        yield UserMessage(content=[ToolResultBlock(tool_use_id, result, error or None)], uuid=str(uuid.uuid4()),
                          parent_tool_use_id=None, tool_use_result=f"Error: {self._result}" if error else result)

    async def _hooks(self, event, call):
        """The options' hooks for this event and tool, as the CLI calls them; their hookSpecificOutput dicts."""
        data = {"session_id": self.session_id, "transcript_path": "", "cwd": str(self.options.cwd),
                "permission_mode": self.options.permission_mode or "default", "hook_event_name": event, **call}
        outputs = []
        for matcher in (self.options.hooks or {}).get(event, []):
            if matcher.matcher and not re.fullmatch(matcher.matcher, call["tool_name"]):
                continue
            for hook in matcher.hooks:
                outputs.append(((await hook(data, call["tool_use_id"], {"signal": None})) or {})
                               .get("hookSpecificOutput", {}))
        return outputs

    async def _run(self, name, tool_input):
        """The tool itself: (result, is_error). MCP tools are called through MCP, Edit, Write and Read act on the
        files; others never run."""
        if name.startswith("mcp__"):
            _, server, tool = name.split("__", 2)
            async with Client(self.options.mcp_servers[server]["instance"]) as client:
                r = await client.call_tool(tool, tool_input)
            # MCP content as the CLI hands it to the model
            return [{"type": "image", "source": {"type": "base64", "media_type": b.mime_type, "data": b.data}}
                    if b.type == "image" else {"type": "text", "text": b.text} for b in r.content], bool(r.is_error)
        path = Path(self.options.cwd, str(tool_input.get("file_path", "")))
        try:
            if name == "Write":
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(tool_input["content"].encode("utf-8"))
                return f"File created successfully at: {path}", False
            if name == "Edit":
                text = path.read_bytes().decode("utf-8")
                old, new = tool_input["old_string"], tool_input["new_string"]
                if old not in text:
                    return "<tool_use_error>String to replace not found in file.</tool_use_error>", True
                path.write_bytes(text.replace(old, new, -1 if tool_input.get("replace_all") else 1).encode("utf-8"))
                return f"The file {path} has been updated successfully.", False
            if name == "Read":
                return path.read_text(encoding="utf-8", errors="replace"), False
        except OSError as e:  # a tool error for the agent, as in the CLI
            return f"<tool_use_error>{e}</tool_use_error>", True
        return f"(simulado: o agente de teste não roda {name})", False

    def _rate(self, rate):
        """As the CLI sends it on a subscription: per-window utilization (0..1) under unifiedWindows."""
        resets_at = int(time.time()) + 3600
        windows = {k: {"utilization": v, "resetsAt": resets_at, "status": "allowed"} for k, v in rate.items()}
        info = {"status": "allowed", "resetsAt": resets_at, "rateLimitType": "five_hour", "isUsingOverage": False,
                "unifiedWindows": windows}
        return RateLimitEvent(rate_limit_info=RateLimitInfo(status="allowed", resets_at=resets_at,
                                                            rate_limit_type="five_hour", raw=info), **self._meta())
