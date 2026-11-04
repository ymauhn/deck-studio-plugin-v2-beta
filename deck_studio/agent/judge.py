"""The judge (pedido da Fase 1, 2026-11-04): a separate, read-only Claude session that reviews the finished deck
against the project's qa/RUBRICA.md and lists what to fix, slide by slide.

Why a session of its own: Deck Studio's write guard denies subagents (undo would not cover their edits), and a judge
that shares the author agent's context grades its own work. This one can only Read, Glob and Grep inside the project;
every other tool is refused by can_use_tool. Its prompt is the project's .claude/agents/juiz-de-slides.md, the same
file the Claude Code plugin of phase 2 uses as a subagent. Its verdict goes to qa/JUIZ.md (written by the studio, not
by the judge), and its cost to the data dir's costs.jsonl."""
import json
import re
import time
from pathlib import Path

from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, PermissionResultAllow, PermissionResultDeny,
                              ResultMessage, TextBlock, query)

AGENT = ".claude/agents/juiz-de-slides.md"
READ_TOOLS = {"Read", "Glob", "Grep"}
TASK = ("Avalie o deck deste projeto agora, seguindo as suas instruções e qa/RUBRICA.md. Leia qa/results.json, "
        "qa/number_audit.md, docs/briefing.json, docs/STORYLINE.md, docs/FACTS.md, docs/FIGURES.md, as fontes dos "
        "slides em deck/src/slides/ e as imagens qa/contact-light.png e qa/shots/light/*.png. Responda só com o "
        "relatório no formato pedido.")


def log_cost(state, kind, result, extra=None):
    """One line of the data dir's costs.jsonl: what a turn (or the judge) cost, as the SDK reports it."""
    line = {"ts": time.time(), "kind": kind, "costUsd": result.total_cost_usd, "usage": result.usage,
            "durationMs": result.duration_ms, "turns": result.num_turns, **(extra or {})}
    with open(Path(state.data_dir) / "costs.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def _prompt(kit):
    text = (kit / AGENT).read_text(encoding="utf-8")
    return re.sub(r"^---\n.*?\n---\n", "", text, count=1, flags=re.S)  # the frontmatter is for Claude Code


async def judge(state, focus=""):
    """The judge's report (markdown), also written to qa/JUIZ.md."""
    kit = Path(state.kit_root)
    if not (kit / AGENT).is_file() or not (kit / "qa" / "RUBRICA.md").is_file():
        raise ValueError(f"This project has no judge: {AGENT} and qa/RUBRICA.md are missing.")
    if state.fake_agent:  # tests: no real session
        report = "# Juiz\n\n(agente de teste) Nenhum item bloqueante.\n"
    else:
        root = kit.resolve()

        async def can_use_tool(name, tool_input, context):
            path = tool_input.get("file_path") or tool_input.get("path") or str(root)
            inside = (root / path).resolve().is_relative_to(root)
            if name in READ_TOOLS and inside:
                return PermissionResultAllow()
            return PermissionResultDeny(message="O juiz só lê os arquivos do projeto.")

        options = ClaudeAgentOptions(
            cwd=str(root), model=state.settings.get("model") or "opus", system_prompt=_prompt(kit),
            # no allowed_tools: those would be approved before can_use_tool runs, reads outside the project included
            disallowed_tools=["Bash", "PowerShell", "Write", "Edit", "MultiEdit", "NotebookEdit", "WebFetch",
                              "WebSearch", "Task", "Agent", "TodoWrite"],
            can_use_tool=can_use_tool, setting_sources=[], max_turns=40,
            env={"CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1", "ENABLE_CLAUDEAI_MCP_SERVERS": "false"})
        texts, result = [], None

        async def prompt():
            yield {"type": "user", "message": {"role": "user", "content": TASK + (f"\n\nFoco: {focus}" if focus else "")}}

        async for m in query(prompt=prompt(), options=options):
            if isinstance(m, AssistantMessage):
                texts += [b.text for b in m.content if isinstance(b, TextBlock)]
            elif isinstance(m, ResultMessage):
                result = m
        report = (texts[-1] if texts else "") or "# Juiz\n\n(o juiz não respondeu)\n"
        if result:
            log_cost(state, "judge", result)
    (kit / "qa").mkdir(exist_ok=True)
    (kit / "qa" / "JUIZ.md").write_text(report.rstrip() + "\n", encoding="utf-8")
    return report
