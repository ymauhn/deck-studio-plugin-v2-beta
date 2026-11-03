import re

from deck_studio.core.source_edit import EditResult, locate_element, replace_text, set_attribute

# Small part files modeled on deck/src/slides: 01-motivation.html is LF.
LF = "\n".join([
    '<section class="slide" id="s03" data-part="1 · Motivation">',
    '<h2 class="title">Millions of sequences, few known functions</h2>',
    '<div class="bd">',
    '  <ul class="b col-a">',
    '    <li class="f" data-f="1">Proteins take part in almost every cellular process</li>',
    '    <li class="f" data-f="2">Sequencing is fast; experimental characterization is slow</li>',
    '  </ul>',
    '</div>',
    '</section>',
    '',
])

# 03-data.html is CRLF.
CRLF = "\r\n".join([
    '<section class="slide" id="s13" data-part="3 · Data and evaluation">',
    '<h2 class="title">Data: a CAFA5-derived corpus</h2>',
    '<div class="bd">',
    '  <div class="f" data-f="1" style="grid-column: 1 / 8">',
    '    <div class="tbl lg" data-table="corpus"></div>',
    '  </div>',
    '  <ul class="b" style="grid-column: 8 / 13">',
    '    <li class="f" data-f="2">80 / 10 / 10 split, disjoint at protein level</li>',
    '    <li class="f" data-f="3">Labels per protein (mean): 25.91 BP, 12.48 CC, 7.55 MF</li>',
    '    <li class="f" data-f="3">Label matrix density:',
    '      <span class="dens"><span class="num">BP</span><i class="dbar" style="--v:5.18"></i></span>',
    '      <!-- CC and MF bars follow -->',
    '    </li>',
    '  </ul>',
    '</div>',
    '</section>',
    '',
])


def test_locate_element_finds_the_element_whose_start_tag_begins_at_line_col_in_an_lf_file():
    el = locate_element(LF, 5, 5)
    assert el.tag == "li"
    assert el.attrs == {"class": "f", "data-f": "1"}
    assert LF[el.start:el.end] == '<li class="f" data-f="1">Proteins take part in almost every cellular process</li>'
    assert LF[el.start:el.start_tag_end] == '<li class="f" data-f="1">'
    assert len(el.children) == 1
    assert el.children[0].index == 0
    assert el.children[0].type == "text"
    assert LF[el.children[0].start:el.children[0].end] == "Proteins take part in almost every cellular process"


def test_locate_element_counts_crlf_line_endings_as_one_line_and_returns_raw_offsets():
    el = locate_element(CRLF, 9, 5)
    assert CRLF[el.start:el.end] == '<li class="f" data-f="3">Labels per protein (mean): 25.91 BP, 12.48 CC, 7.55 MF</li>'
    mixed = locate_element(CRLF, 10, 5)
    assert [c.type for c in mixed.children] == ["text", "element", "text", "comment", "text"]
    assert CRLF[mixed.children[0].start:mixed.children[0].end] == "Label matrix density:\r\n      "


def test_locate_element_resolves_the_s13_bullet_in_a_copy_of_the_real_03_data_html(kit_copy):
    html = (kit_copy / "deck/src/slides/03-data.html").read_bytes().decode("utf-8")
    el = locate_element(html, 9, 5)
    assert el.tag == "li"
    text = el.children[0]
    assert html[text.start:text.end] == "Labels per protein (mean): 25.91 BP, 12.48 CC, 7.55 MF"


def test_replace_text_replaces_only_the_text_node_and_keeps_every_other_byte():
    r = replace_text(LF, line=5, col=5, child_index=0, old_text="Proteins take part in almost every cellular process", new_text="Proteins act in almost every cellular process")
    assert r == EditResult(ok=True, html=LF.replace("Proteins take part in", "Proteins act in"))


def test_replace_text_in_a_crlf_file_keeps_every_crlf_and_adds_no_bare_lf():
    r = replace_text(CRLF, line=9, col=5, child_index=0, old_text="Labels per protein (mean): 25.91 BP, 12.48 CC, 7.55 MF", new_text="Mean labels per protein: 25.91 BP, 12.48 CC, 7.55 MF")
    assert r.html == CRLF.replace("Labels per protein (mean):", "Mean labels per protein:")
    assert r.html.count("\r\n") == CRLF.count("\r\n")
    assert len(re.findall(r"(?<!\r)\n", r.html)) == 0


def test_replace_text_keeps_the_raw_text_nodes_leading_and_trailing_whitespace():
    # the browser saw the text with LF and may send it with its surrounding whitespace
    r = replace_text(CRLF, line=10, col=5, child_index=0, old_text="Label matrix density:\n      ", new_text=" Label density: ")
    assert r.html == CRLF.replace("Label matrix density:\r\n      <span", "Label density:\r\n      <span")
    cap = '<figcaption class="cap">\n  Dissertation, Fig. 2.1\n</figcaption>\n'
    c = replace_text(cap, line=1, col=1, child_index=0, old_text="Dissertation, Fig. 2.1", new_text="Dissertation, Fig. 2.2")
    assert c.html == '<figcaption class="cap">\n  Dissertation, Fig. 2.2\n</figcaption>\n'


def test_replace_text_escapes_amp_lt_and_gt_in_the_new_text():
    r = replace_text(LF, line=5, col=5, child_index=0, old_text="Proteins take part in almost every cellular process", new_text="BP < CC & MF > 0")
    assert r.html == LF.replace("Proteins take part in almost every cellular process", "BP &lt; CC &amp; MF &gt; 0")


def test_replace_text_refuses_as_stale_when_the_source_text_differs_from_what_the_browser_saw():
    r = replace_text(LF, line=5, col=5, child_index=0, old_text="Proteins take part in every process", new_text="x")
    assert r.ok is False
    assert r.code == "stale"
    assert isinstance(r.message, str)
    assert r.html is None
    # differences in whitespace only are not stale
    ws = replace_text(LF, line=5, col=5, child_index=0, old_text=" Proteins  take part\n in almost every cellular process ", new_text="x")
    assert ws.ok is True


def test_replace_text_refuses_a_raw_text_node_that_contains_an_entity():
    # modeled on 06-conclusions.html, which writes ">" as &gt;
    rq = "\n".join([
        '<div class="rq f" data-f="1">',
        '  <span><small>Fixed vs learned aggregation</small>Late 67.06 &gt; Early 65.84 &gt; Fixed 65.12</span>',
        '</div>',
        '',
    ])
    r = replace_text(rq, line=2, col=3, child_index=1, old_text="Late 67.06 > Early 65.84 > Fixed 65.12", new_text="Late 67.06 > Early 65.84")
    assert r.ok is False
    assert r.code == "entities"
    assert isinstance(r.message, str)


def test_replace_text_refuses_a_child_that_is_an_element_or_a_comment():
    for child_index in [1, 3]:
        r = replace_text(CRLF, line=10, col=5, child_index=child_index, old_text="BP", new_text="x")
        assert r.code == "not-text", f"child {child_index}"
        assert r.ok is False


def test_replace_text_reports_not_found_when_no_element_starts_at_line_col_or_the_child_is_missing():
    assert locate_element(LF, 5, 4) is None
    for at in [{"line": 5, "col": 4, "child_index": 0}, {"line": 99, "col": 1, "child_index": 0}, {"line": 5, "col": 5, "child_index": 1}]:
        r = replace_text(LF, **at, old_text="Proteins take part in almost every cellular process", new_text="x")
        assert r.code == "not-found", at
        assert r.ok is False


def test_replace_text_refuses_math_tables_and_anything_in_a_component_as_not_editable():
    # modeled on 02-background.html, 03-data.html and 04-method.html
    gen = "\n".join([
        '<section class="slide" id="s08" data-part="2 · Background and related work">',
        '<div class="bd">',
        '  <ul class="b col-a">',
        '    <li class="f" data-f="1">',
        '      <span class="m">G = (V, E, w)</span>: proteins, associations, STRING confidence',
        '    </li>',
        '  </ul>',
        '  <div class="m d">\\tilde{s}_{iv} = \\max_{u} s_{iu}</div>',
        '  <div class="tbl lg" data-table="corpus"></div>',
        '  <div class="col-w" data-component="INT-PIPE" style="height:540px">',
        '    <p class="cap">Routes: <b>Fixed</b> and GNN</p>',
        '  </div>',
        '</div>',
        '</section>',
        '',
    ])
    cases = {
        "span.m": {"line": 5, "col": 7, "old_text": "G = (V, E, w)"},
        "div.m.d": {"line": 8, "col": 3, "old_text": "\\tilde{s}_{iv} = \\max_{u} s_{iu}"},
        "div.tbl": {"line": 9, "col": 3, "old_text": ""},
        "[data-component]": {"line": 10, "col": 3, "old_text": ""},
        "p inside [data-component]": {"line": 11, "col": 5, "old_text": "Routes:"},
        "b inside [data-component]": {"line": 11, "col": 28, "old_text": "Fixed"},
    }
    for name, at in cases.items():
        r = replace_text(gen, **at, child_index=0, new_text="x")
        assert r.code == "not-editable", name
        assert isinstance(r.message, str)
    # the plain text right after the math stays editable
    li = replace_text(gen, line=4, col=5, child_index=2, old_text=": proteins, associations, STRING confidence", new_text=": proteins and associations")
    assert li.html == gen.replace(": proteins, associations, STRING confidence", ": proteins and associations")


def test_replace_text_writes_a_line_break_in_the_new_text_with_the_files_own_line_ending():
    r = replace_text(CRLF, line=9, col=5, child_index=0, old_text="Labels per protein (mean): 25.91 BP, 12.48 CC, 7.55 MF", new_text="Labels per protein (mean):\n25.91 BP, 12.48 CC, 7.55 MF")
    assert r.html == CRLF.replace("Labels per protein (mean): 25.91", "Labels per protein (mean):\r\n25.91")
    lf = replace_text(LF, line=5, col=5, child_index=0, old_text="Proteins take part in almost every cellular process", new_text="Proteins take part\r\nin every process")
    assert lf.html == LF.replace("Proteins take part in almost every cellular process", "Proteins take part\nin every process")


def test_replace_text_in_a_mixed_eol_file_keeps_every_byte_except_the_replaced_text():
    mixed = '<ul class="b">\r\n  <li class="f">One</li>\n  <li class="f">Two</li>\r\n</ul>\n'
    r = replace_text(mixed, line=3, col=3, child_index=0, old_text="Two", new_text="Three")
    assert r.html == mixed.replace("Two", "Three")


def test_locate_element_honors_a_self_closing_slash_only_on_void_and_svg_elements_as_parse5_does():
    html = '<div class="a"/><span>in</span></div>\n<svg><rect/>t</svg>\n'
    div = locate_element(html, 1, 1)
    assert html[div.start:div.end] == '<div class="a"/><span>in</span></div>'
    assert [c.type for c in div.children] == ["element"]
    rect = locate_element(html, 2, 6)
    assert html[rect.start:rect.end] == "<rect/>"
    assert rect.children == []


# set_attribute ([drag]): one attribute of the element at line:col, every other byte as it was


def test_set_attribute_adds_a_missing_attribute_after_the_last_one_and_keeps_every_other_byte():
    r = set_attribute(CRLF, 8, 5, "style", "translate: 0 24px")
    assert r == EditResult(ok=True, html=CRLF.replace('<li class="f" data-f="2">80 / 10',
                                                      '<li class="f" data-f="2" style="translate: 0 24px">80 / 10'))


def test_set_attribute_replaces_the_value_of_an_existing_attribute_where_it_is():
    r = set_attribute(CRLF, 7, 3, "style", "grid-column: 6 / 13")
    assert r.html == CRLF.replace('<ul class="b" style="grid-column: 8 / 13">', '<ul class="b" style="grid-column: 6 / 13">')
    assert set_attribute(LF, 4, 3, "class", "b col-b").html == LF.replace('<ul class="b col-a">', '<ul class="b col-b">')
    # quotes of any kind, no value at all, any case, attributes across lines: the first of duplicates counts, as in parse5
    tag = "<div\r\n  CLASS=a hidden\r\n  Style='x: 1' style=\"y\">t</div>\r\n"
    assert set_attribute(tag, 1, 1, "class", "b").html == tag.replace("CLASS=a", 'CLASS="b"')
    assert set_attribute(tag, 1, 1, "hidden", "").html == tag.replace("hidden", 'hidden=""')
    assert set_attribute(tag, 1, 1, "style", "z").html == tag.replace("Style='x: 1'", 'Style="z"')


def test_set_attribute_with_none_removes_the_attribute_and_the_space_before_it():
    assert set_attribute(CRLF, 7, 3, "style", None).html == CRLF.replace('<ul class="b" style="grid-column: 8 / 13">', '<ul class="b">')
    assert set_attribute(CRLF, 7, 3, "class", None).html == CRLF.replace('<ul class="b" style=', '<ul style=')
    tag = '<div\r\n  class="a"\r\n  style="y">t</div>\r\n'
    assert set_attribute(tag, 1, 1, "style", None).html == '<div\r\n  class="a">t</div>\r\n'
    assert set_attribute(LF, 5, 5, "style", None) == EditResult(ok=True, html=LF)  # nothing to remove


def test_set_attribute_escapes_the_value_so_it_reads_back_as_given():
    value = 'a "b" & <c>\r\nd'
    r = set_attribute(LF, 5, 5, "title", value)
    assert r.html == LF.replace('<li class="f" data-f="1">', '<li class="f" data-f="1" title="a &quot;b&quot; &amp; &lt;c&gt;&#13;&#10;d">')
    assert locate_element(r.html, 5, 5).attrs["title"] == value


def test_set_attribute_adds_to_void_and_self_closing_tags_before_their_end():
    html = '<figure>\n  <img src="img/fig.webp" alt="A plot" />\n  <br/><hr>\n</figure>\n'
    assert set_attribute(html, 2, 3, "style", "width: 480px").html == html.replace(
        'alt="A plot" />', 'alt="A plot" style="width: 480px" />')
    assert set_attribute(html, 3, 3, "class", "x").html == html.replace("<br/>", '<br class="x"/>')
    assert set_attribute(html, 3, 8, "class", "x").html == html.replace("<hr>", '<hr class="x">')


def test_set_attribute_reports_not_found_and_refuses_math_tables_and_component_internals():
    r = set_attribute(LF, 5, 4, "style", "x")
    assert (r.ok, r.code, r.html) == (False, "not-found", None)
    assert isinstance(r.message, str)
    gen = "\n".join([
        '<div class="bd">',
        '  <p class="small">IC: <span class="m">-\\log_2 p</span></p>',
        '  <div class="m d">\\max_{\\tau} F</div>',
        '  <div class="tbl lg" data-table="corpus"></div>',
        '  <div class="col-w" data-component="INT-PIPE" style="height:540px">',
        '    <img class="pipe-fig" src="img/fig_5_6.webp" alt="">',
        '  </div>',
        '</div>',
        '',
    ])
    for name, (line, col) in {"span.m": (2, 24), "div.m.d": (3, 3), "div.tbl": (4, 3), "img in [data-component]": (6, 5)}.items():
        r = set_attribute(gen, line, col, "style", "translate: 0 8px")
        assert (r.ok, r.code) == (False, "not-editable"), name
        assert isinstance(r.message, str)
    # the component itself and the box around inline math are authored boxes
    assert set_attribute(gen, 5, 3, "class", "col-b").html == gen.replace('class="col-w"', 'class="col-b"')
    assert set_attribute(gen, 2, 3, "style", "width: 480px").ok is True


def test_set_attribute_on_a_copy_of_the_real_02_background_html_changes_only_that_start_tag(kit_copy):
    html = (kit_copy / "deck/src/slides/02-background.html").read_bytes().decode("utf-8")
    start = '  <div class="col-w" data-component="INT-RW" style="height:630px"\r\n    data-opts=\'{"statement":'
    assert html.count(start) == 1
    r = set_attribute(html, 70, 3, "style", "height:630px; translate: 0 16px")
    assert r.html == html.replace(start, start.replace('"height:630px"', '"height:630px; translate: 0 16px"'))
    tail = ' SEGT-GO"}\'></div>'
    assert html.count(tail) == 1
    r = set_attribute(html, 70, 3, "title", "x")
    assert r.html == html.replace(tail, ' SEGT-GO"}\' title="x"></div>')
