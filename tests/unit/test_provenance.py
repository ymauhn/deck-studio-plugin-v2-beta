import re

from deck_studio.provenance import build_index

TEX = "source/thesis/dissertation.tex"


def numbers(index, slide):
    return {e["number"]: e for e in index["slides"][slide]}


def add_to_s13(kit, markup):
    part = kit / "deck/src/slides/03-data.html"
    text = part.read_text(encoding="utf8")
    at = text.index(">", text.index('id="s13"')) + 1
    part.write_text(text[:at] + markup + text[at:], encoding="utf8")


def test_s13_labels_per_protein_point_to_tex_lines_that_contain_them(kit_copy):
    tex = (kit_copy / TEX).read_text(encoding="utf8").split("\n")
    s13 = numbers(build_index(kit_copy), "s13")
    for n in ("25.91", "12.48", "7.55"):
        assert s13[n]["sources"] and s13[n]["reason"] is None
        for src in s13[n]["sources"]:
            assert src["file"] == TEX
            assert n in tex[src["line"] - 1]
            assert n in src["snippet"]


def test_a_small_number_points_first_to_the_tex_line_that_also_holds_the_numbers_beside_it(kit_copy):
    # the defense date as dissertation.tex has it, on a slide of the test's own: the title slide shows the date the
    # author gives (docs/FACTS.md, November 16 since 2026-10-28), which the .tex does not hold
    (kit_copy / "deck/src/slides/99-date.html").write_text(
        '<section class="slide" id="s99"><p>Defense · November 5, 2026</p></section>\n', encoding="utf8")
    tex = (kit_copy / TEX).read_text(encoding="utf8").split("\n")
    index = build_index(kit_copy)
    first = lambda slide, n: tex[numbers(index, slide)[n]["sources"][0]["line"] - 1]
    # s14 "Degree is heavy-tailed: median 5 to 7, maximum 763 to 805": over a hundred .tex lines hold a 5,
    # the first of them in file order is the defense date, and a 7 comes first in a comment
    for n in ("5", "7"):
        assert re.match(r"\s*\\quad Median\s*&\s*5\s*&\s*7\s*&\s*7\s*\\\\", first("s14", n)), n
    # a date's 5 is the defense date, next to 2026
    assert first("s99", "5").startswith("\\datadadefesa{05}{11}{2026}")


def test_sources_are_loose_when_the_tex_has_the_number_only_inside_another_term_or_in_a_comment(kit_copy):
    tex = kit_copy / TEX
    added = ["ProtT98765 runs on a 98765.5cm page", "% 87654 only in a comment", "X76543 inside a word",
             "76543 on its own"]
    tex.write_text(tex.read_text(encoding="utf8").rstrip("\n") + "\n" + "\n".join(added) + "\n", encoding="utf8")
    at = {line: n for n, line in enumerate(tex.read_text(encoding="utf8").split("\n"), 1)}
    add_to_s13(kit_copy, "<p>98765, 87654 and 76543</p>")

    s13 = numbers(build_index(kit_copy), "s13")
    sources = lambda n: [(src["line"], src["loose"]) for src in s13[n]["sources"]]
    assert sources("98765") == [(at[added[0]], True)]
    assert sources("87654") == [(at[added[1]], True)]
    assert sources("76543") == [(at[added[3]], False)]
    assert {src["loose"] for src in s13["25.91"]["sources"]} == {False}


def test_visapp_page_number_carries_the_audit_reason(kit_copy):
    s07 = numbers(build_index(kit_copy), "s07")
    assert s07["157"] == {"number": "157", "sources": [], "reason": "VISAPP pages"}


def test_every_number_on_the_real_deck_has_sources_or_a_reason(kit_copy):
    slides = build_index(kit_copy)["slides"]
    assert {f"s{i:02d}" for i in range(1, 46)} <= slides.keys()
    orphans = [(s, e["number"]) for s, es in slides.items() for e in es if not e["sources"] and not e["reason"]]
    assert orphans == []


def test_a_number_the_tex_lacks_comes_back_with_no_sources_and_no_reason(kit_copy):
    assert "987.65" not in (kit_copy / TEX).read_text(encoding="utf8")
    assert "987.65" not in numbers(build_index(kit_copy), "s13")
    add_to_s13(kit_copy, "<p>Invented: 987.65</p>")
    s13 = numbers(build_index(kit_copy), "s13")
    assert s13["987.65"] == {"number": "987.65", "sources": [], "reason": None}


def test_numbers_in_speaker_notes_and_math_are_not_on_the_slide(kit_copy):
    add_to_s13(kit_copy, '<p><span class="m">x^{987.65}</span></p><div class="m d">y = 876.54</div>'
                         '<aside class="notes"><p>Say 765.43</p></aside>')
    s13 = numbers(build_index(kit_copy), "s13")
    assert not {"987.65", "876.54", "765.43"} & s13.keys()
    assert "25.91" in s13


def test_unmatched_and_illustrative_audit_rows_are_not_reasons(kit_copy):
    audit = kit_copy / "qa/number_audit.md"
    audit.write_text(audit.read_text(encoding="utf8") + "| 13 | 987.65 | UNMATCHED |\n"
                     "| 5 | 876.54 | illustrative component (labelled on screen) |\n", encoding="utf8")
    add_to_s13(kit_copy, "<p>987.65 and 876.54</p>")
    s13 = numbers(build_index(kit_copy), "s13")
    assert s13["987.65"] == {"number": "987.65", "sources": [], "reason": None}
    assert s13["876.54"] == {"number": "876.54", "sources": [], "reason": None}


def test_sources_are_short_enough_for_a_chip(kit_copy):
    entries = [e for es in build_index(kit_copy)["slides"].values() for e in es]
    assert max(len(e["sources"]) for e in entries) == 5
    assert all(len(src["snippet"]) <= 160 for e in entries for src in e["sources"])
