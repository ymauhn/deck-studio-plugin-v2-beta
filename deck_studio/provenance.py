"""Number provenance: each number on each slide, with the dissertation.tex lines that hold it.

The number rules port the kit's qa/audit_numbers.py (docs/QA.md §3); the kit file is never imported.
"""
import html
import re
from functools import lru_cache
from pathlib import Path

TEX = "source/thesis/dissertation.tex"
SLIDES = "deck/src/slides"
AUDIT = "qa/number_audit.md"
AUDIT_ROW = re.compile(r"^\| *B?\d+ *\|([^|\n]+)\|([^|\n]+)\|", re.M)  # | slide | number(s) | reason |
# the audit's allow list is global, so a row's reason holds on any slide; these two rows allow nothing in
# slide sources (demo values are drawn by components at run time)
NOT_REASONS = {"UNMATCHED", "illustrative component (labelled on screen)"}
SLIDE_NUM = re.compile(r"(?<![\w.])\d+(?:,\d{3})*(?:\.\d+)?(?![\w])")
TEX_NUM = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")  # the audit's .tex rule: also inside "ProtT5" or "10pt"
OWN_NUM = re.compile(r"(?<![\w.])\d+(?:,\d{3})*(?:\.\d+)?(?!\w|\.\d)")  # a number of its own: no 2 in "2.5cm"
COMMENT = re.compile(r"(?<!\\)%.*")
ATTRS = r"""(?:[^>"']|"[^"]*"|'[^']*')*"""
SECTION = re.compile(rf"<section\b({ATTRS})>(.*?)</section>", re.S)
TAG = re.compile(rf"<{ATTRS}>")
# speaker notes, and the math placeholders that deck/build.mjs renders as SVG (no text on the slide)
NOT_SHOWN = re.compile(r'<aside class="notes"[^>]*>.*?</aside>|<div class="m d">.*?</div>|<span class="m">.*?</span>', re.S)
MAX_SOURCES = 5


def build_index(kit_root, slides=SLIDES):
    """{"slides": {id: [{"number", "sources", "reason"}]}}; rebuilt only when an input file changes. Do not mutate it.
    `slides` is the slides folder on screen (deck/src-pt/slides with the Portuguese deck)."""
    kit = Path(kit_root)
    files = [kit / TEX, kit / AUDIT, *sorted((kit / slides).glob("*.html"))]
    return _build(kit, slides, tuple(map(_stamp, files)))


def _stamp(path):
    st = path.stat()
    return str(path), st.st_mtime_ns, st.st_size


def canon(number):
    return repr(round(float(number.replace(",", "")), 6))


def snippet(line, start, end, pad=60):
    a, b = max(0, start - pad), end + pad
    return ("…" if a else "") + " ".join(line[a:b].split()) + ("…" if b < len(line) else "")


@lru_cache(maxsize=4)
def _build(kit, slides_dir, _stamps):
    lines = [re.sub(r"(\d)\\,(\d)", r"\1\2", line.replace("{,}", ","))
             for line in (kit / TEX).read_text(encoding="utf8").split("\n")]
    # canon -> {line: span of the first match there}: the numbers of their own in the text of each line, and
    # the loose ones the audit also counts (inside other terms, in comments)
    own, loose = {}, {}
    holds = []  # the numbers of their own on each line
    for n, line in enumerate(lines, 1):
        holds.append(set())
        for m in OWN_NUM.finditer(COMMENT.sub("", line)):
            own.setdefault(canon(m.group()), {}).setdefault(n, m.span())
            holds[-1].add(canon(m.group()))
        for m in TEX_NUM.finditer(line):
            loose.setdefault(canon(m.group()), {}).setdefault(n, m.span())
    reasons = {}
    for numbers, why in AUDIT_ROW.findall((kit / AUDIT).read_text(encoding="utf8")):
        if why.strip() not in NOT_REASONS:
            for v in numbers.split():
                reasons.setdefault(v, why.strip())

    def entry(number, beside):
        """The lines that hold the number of its own, else its loose ones; those that also hold the numbers
        beside it on the slide come first."""
        c = canon(number)
        hits = own.get(c) or loose.get(c, {})
        best = sorted(hits, key=lambda n: (-len(beside & holds[n - 1]), n))[:MAX_SOURCES]
        sources = [{"file": TEX, "line": n, "snippet": snippet(lines[n - 1], *hits[n]), "loose": c not in own}
                   for n in best]
        return {"number": number, "sources": sources, "reason": None if sources else reasons.get(number)}

    slides = {}
    for part in sorted((kit / slides_dir).glob("*.html")):
        for attrs, body in SECTION.findall(part.read_text(encoding="utf8")):
            if sid := re.search(r'\sid="([^"]+)"', attrs):
                text = html.unescape(TAG.sub(" ", NOT_SHOWN.sub(" ", body)))
                rows = [SLIDE_NUM.findall(row) for row in text.split("\n")]  # a source line: a bullet, a cell, a caption
                slides[sid[1]] = [entry(v, {canon(w) for row in rows if v in row for w in row})
                                  for v in dict.fromkeys(v for row in rows for v in row)]
    return {"slides": slides}
