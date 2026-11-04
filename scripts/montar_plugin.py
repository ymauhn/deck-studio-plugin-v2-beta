"""Monta o plugin do Claude Code em plugin/ a partir do Deck Studio (etapa 4, docs/plano-etapas-2-4-5.md).

Uso: python scripts/montar_plugin.py            copia e adapta
     python scripts/montar_plugin.py --check    só confere: sai com 1 se o plugin/ está diferente do que sairia

A fonte única é o deck_studio: as skills e o juiz do modelo de projeto, o próprio modelo e os módulos que o servidor
MCP do plugin usa. O que este script gera fica em plugin/plugins/deck-studio/ e não se edita lá (cada arquivo de texto
gerado leva o aviso). O resto de plugin/ (plugin.json, .mcp.json, hooks, as skills próprias do plugin, o servidor
deck_tools, README, LICENSE) é escrito à mão. Só a biblioteca padrão.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "deck_studio"
PLUGIN = ROOT / "plugin" / "plugins" / "deck-studio"
SKILLS = SRC / "templates" / "project" / ".claude" / "skills"
AGENT = SRC / "templates" / "project" / ".claude" / "agents" / "juiz-de-slides.md"
TOOL = "mcp__plugin_deck-studio_deck__"  # what Claude Code names a plugin MCP server's tools
# the modules the plugin's server imports (deck_tools), and what they import in turn; never the Agent SDK, the chat,
# the app's entry point (__main__: it names the author's kit) nor its project panel
MODULES = ["__init__.py", "config.py", "deck_build.py", "pdf_import.py", "projects.py", "render.py",
           "beamer", "core", "templates", "server/__init__.py", "server/api.py", "server/events.py",
           "server/state.py", "features/__init__.py", "features/beamer.py"]
SKIP = {"__pycache__", ".claude"}  # the template's skills and judge are the plugin's own (skills/, agents/)
TEXT = {".md", ".py", ".html", ".css", ".js", ".json", ".tex", ".txt", ".sty", ".bib"}


def adapt(text):
    """The project skills' words for the plugin: its tools' names, the judge as a subagent, the skills by name."""
    text = text.replace(
        "(com a ferramenta Read, em `.claude/skills/<nome>/SKILL.md`)",
        "(pela ferramenta Skill, como `deck-studio:<nome>`)")
    text = text.replace(
        "2. Chame `mcp__deck__judge_deck`. O juiz é uma sessão separada, que só lê o projeto e segue `qa/RUBRICA.md`.",
        "2. Chame o subagente `deck-studio:juiz` (ferramenta Agent). Ele não fez o deck, só lê o projeto e segue "
        "`qa/RUBRICA.md`; grave o relatório dele, como veio, em `qa/JUIZ.md`.")
    text = text.replace("`mcp__deck__run_qa` and `mcp__deck__judge_deck` until they pass",
                        "`mcp__deck__run_qa` and the `deck-studio:juiz` subagent until they pass")
    text = text.replace("Edit `qa/` and `.claude/agents/` only when the author asks", "Edit `qa/` only when the author asks")
    text = text.replace("`.claude/skills/criar-apresentacao/", "the plugin skill `deck-studio:criar-apresentacao`, file `")
    return text.replace("mcp__deck__", TOOL)


def plan():
    """{path under PLUGIN: bytes} of everything this script owns."""
    out = {}
    for d in sorted(SKILLS.iterdir()):
        for f in sorted(p for p in d.rglob("*") if p.is_file()):
            rel = Path("skills", d.name, f.relative_to(d))
            data = f.read_bytes()
            if f.suffix == ".md":
                data = adapt(data.decode("utf-8")).encode("utf-8")
            out[rel] = data
    agent = adapt(AGENT.read_text(encoding="utf-8")).replace("name: juiz-de-slides", "name: juiz", 1)
    out[Path("agents", "juiz.md")] = agent.encode("utf-8")
    for m in MODULES:
        src = SRC / m
        files = [src] if src.is_file() else sorted(p for p in src.rglob("*") if p.is_file())
        for f in files:
            rel_src = f.relative_to(SRC)
            if SKIP & set(rel_src.parts) or f.suffix in {".pyc"}:
                continue
            data = f.read_bytes()
            if rel_src.parts[0] == "templates" and f.suffix in TEXT:
                data = adapt(data.decode("utf-8")).encode("utf-8")
            out[Path("server", "deck_studio", rel_src)] = data
    return out


def owned():
    """The files under PLUGIN this script wrote (skills and agents it brings, and the vendored package)."""
    roots = [PLUGIN / "server" / "deck_studio", PLUGIN / "agents" / "juiz.md",
             *(PLUGIN / "skills" / d.name for d in SKILLS.iterdir())]
    found = set()
    for r in roots:
        if r.is_file():
            found.add(r.relative_to(PLUGIN))
        elif r.is_dir():
            found |= {p.relative_to(PLUGIN) for p in r.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    return found


def main(check):
    want = plan()
    have = owned()
    stale = sorted(str(p) for p in have - set(want))
    changed = sorted(str(p) for p, data in want.items() if not (PLUGIN / p).is_file() or (PLUGIN / p).read_bytes() != data)
    if check:
        for p in changed:
            print(f"diferente: {p}")
        for p in stale:
            print(f"sobrando: {p}")
        print("plugin/ em dia" if not (changed or stale) else "plugin/ desatualizado: rode scripts/montar_plugin.py")
        return not (changed or stale)
    for p in stale:
        (PLUGIN / p).unlink()
    for p, data in want.items():
        target = PLUGIN / p
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    print(f"plugin/ montado: {len(want)} arquivos, {len(changed)} mudaram, {len(stale)} saíram")
    return True


if __name__ == "__main__":
    sys.exit(0 if main("--check" in sys.argv[1:]) else 1)
