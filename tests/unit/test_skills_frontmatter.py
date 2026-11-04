"""The project template's skills and agents load with their metadata: in YAML, a frontmatter value with ": " in it
must be quoted, or Claude Code drops every field (claude plugin validate: "YAML frontmatter failed to parse")."""
import json
import re

from deck_studio.templates import PROJECT


def test_every_skill_and_agent_frontmatter_parses():
    files = sorted((PROJECT / ".claude").rglob("*.md"))
    heads = [(f, re.match(r"---\n(.*?)\n---\n", f.read_text(encoding="utf-8"), re.S)) for f in files]
    assert sum(1 for f, m in heads if m) >= 8  # 7 skills and the judge
    for f, m in heads:
        if not m:
            continue
        fields = dict(line.split(": ", 1) for line in m[1].split("\n") if ": " in line)
        assert {"name", "description"} <= set(fields), f
        for key, value in fields.items():
            if ": " in value:
                assert value.startswith('"') and json.loads(value), (f, key)
