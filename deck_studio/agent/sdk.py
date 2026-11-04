"""Agent clients: the real ClaudeSDKClient on the author's subscription, or the scripted fake (--fake-agent).

Both get the same ClaudeAgentOptions, so the fake drives the session's real hooks."""
import json
import shutil
from dataclasses import replace
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, HookMatcher

from deck_studio.agent.fake import FakeClient
from deck_studio.agent.prompt import appendix
from deck_studio.agent.tools import deck_server
from deck_studio.core.write_guard import WRITE_TOOLS
from deck_studio.features import approvals

SKILLS_PLUGIN = "deck-studio-skills"  # the app's own plugin, holding copies of the selected user skills
# the default set besides the project skills (docs/PYTHON.md "Skills"): plugin, bundled and user skills
DEFAULT_SKILLS = {"frontend-design:frontend-design", "impeccable:impeccable", "dataviz",
                  f"{SKILLS_PLUGIN}:humanizer", f"{SKILLS_PLUGIN}:thesis-review"}
# every skill bundled with the pinned CLI (2.1.310, read from its init message on 2026-10-27): the unselected ones
# are turned off, or the init message lists them all (skills= only hides them from the model).
# ponytail: a fixed list; refresh it when the SDK pin moves (the live smoke test fails on a new one)
CLI_SKILLS = ["dataviz", "deep-research", "design", "design-sync", "update-config", "verify", "debug", "code-review",
              "simplify", "batch", "fewer-permission-prompts", "doctor", "loop", "schedule", "claude-api",
              "workflow-authoring", "run", "run-skill-generator", "plugin-authoring"]
SETTINGS = {"disableAllHooks": True}  # the author's own hooks; SDK hook callbacks still fire
SHELL_TOOLS = ("Bash", "PowerShell")  # an approved command may change any file, the deck sources included
MAX_LINE = 64 << 20  # bytes: the longest message the SDK reads from the CLI


def make_options(state, model, session):
    """The options of one chat session; its hooks are the session's own. Opus unless a model is given.

    These sessions stay out of the author's own /resume list: the SDK sets CLAUDE_CODE_ENTRYPOINT=sdk-py, and the
    CLI's list leaves out sdk-py sessions (read in the bundled CLI 2.1.310), so `env` must not set that variable."""
    return ClaudeAgentOptions(
        cwd=state.kit_root,
        model=model or state.settings.get("model") or "opus",
        effort=session.effort or None,  # None: the model's own default
        skills=selected_skills(state),
        resume=session.resume,  # by id, never "continue": that would pick the author's own last conversation
        permission_mode="default",  # explicit: the author's own settings default to auto
        setting_sources=["project"],
        strict_mcp_config=True,
        mcp_servers={"deck": deck_server(state, session)},
        # the CLI's own hook timeout must outlast an approval's wait, which ends in a denial
        hooks={"PreToolUse": [HookMatcher(hooks=[session.pre_tool_use], timeout=approvals.timeout(state) + 60)],
               "PostToolUse": [HookMatcher("|".join([*WRITE_TOOLS, *SHELL_TOOLS]), [session.post_tool_use],
                                           timeout=600)]},
        include_partial_messages=True,
        # one stream-json line holds a whole tool result, an image twice (the SDK's default of 1 MiB killed a turn on
        # a 1.27 MB Read of a PNG, 2026-10-28), and a turn's parallel calls can come back in one message
        max_buffer_size=MAX_LINE,
        settings=json.dumps(SETTINGS),
        system_prompt={"type": "preset", "preset": "claude_code", "append": appendix(state.config)},
        env={"CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1", "ENABLE_CLAUDEAI_MCP_SERVERS": "false",
             "ENABLE_TOOL_SEARCH": "false"},  # the deck tools load directly, without a tool search round trip
    )


def make_client(state, model, session):
    """A fresh, unconnected client for one chat session."""
    options = make_options(state, model, session)
    if state.fake_agent:
        return FakeClient(state.fake_agent, options)
    return ClaudeSDKClient(replace(options, **skill_options(state, options.skills)))


def _skill_names(folder):
    return sorted(p.parent.name for p in Path(folder).glob("*/SKILL.md"))


def catalog(state, home=None):
    """Every skill a chat can load, as [{name, source, plugin?}]; `name` is what skills= takes. The sources: the
    project (the kit's .claude/skills, with the skills chats create), the user (~/.claude/skills, loaded through the
    app's own plugin), the installed plugins and the skills bundled with the CLI."""
    home = Path(home or Path.home())
    found = [{"name": n, "source": "project"} for n in _skill_names(state.kit_root / ".claude" / "skills")]
    found += [{"name": f"{SKILLS_PLUGIN}:{n}", "source": "user"} for n in _skill_names(home / ".claude" / "skills")]
    for plugin, path in _installed_plugins(home).items():
        found += [{"name": f"{plugin}:{n}", "source": "plugin", "plugin": plugin}
                  for n in _skill_names(Path(path) / "skills")]
    return found + [{"name": n, "source": "bundled"} for n in CLI_SKILLS]


def selected_skills(state, home=None):
    """The skills of a new session: the author's choice for each skill in settings["skills"] ({name: on}); a skill
    without one (say, a project skill made since) follows the default set, which has every project skill."""
    choices = state.settings.get("skills")
    choices = choices if isinstance(choices, dict) else {}
    return [s["name"] for s in catalog(state, home)
            if choices.get(s["name"], s["source"] == "project" or s["name"] in DEFAULT_SKILLS)]


def skill_options(state, skills, home=None):
    """plugins= and settings= for these skills: the plugins they come from, and the unselected bundled skills off."""
    home = Path(home or Path.home())
    installed = _installed_plugins(home)
    plugins, user_skills = [], []
    for name in skills:
        plugin, _, skill = name.rpartition(":")
        if plugin == SKILLS_PLUGIN:
            user_skills.append(skill)
        elif plugin and plugin in installed and {"type": "local", "path": installed[plugin]} not in plugins:
            plugins.append({"type": "local", "path": installed[plugin]})
    if user_skills:
        plugins.append({"type": "local", "path": str(_skills_plugin(state.data_dir, home, user_skills))})
    overrides = {s: "off" for s in CLI_SKILLS if s not in skills}
    return {"plugins": plugins, "settings": json.dumps({**SETTINGS, "skillOverrides": overrides})}


def _installed_plugins(home):
    """plugin name -> installPath, from ~/.claude/plugins/installed_plugins.json (user-scope installs first)."""
    found = {}
    try:
        registry = json.loads((home / ".claude" / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
        for key, installs in registry.get("plugins", {}).items():
            for install in sorted(installs, key=lambda i: i.get("scope") != "user"):
                found.setdefault(key.split("@")[0], install["installPath"])
    except (OSError, ValueError, AttributeError, KeyError, TypeError):  # no plugins rather than no chat
        pass
    return found


def _skills_plugin(data_dir, home, names):
    """A local plugin in the app data holding copies of the selected user skills."""
    root = Path(data_dir) / "skills-plugin"
    shutil.rmtree(root, ignore_errors=True)
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text(json.dumps(
        {"name": SKILLS_PLUGIN, "description": "User skills selected in Deck Studio", "version": "1.0.0"}),
        encoding="utf-8")
    for name in names:
        source = home / ".claude" / "skills" / name
        if (source / "SKILL.md").is_file():
            shutil.copytree(source, root / "skills" / name)
    return root
