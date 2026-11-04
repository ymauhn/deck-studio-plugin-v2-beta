"""Seam 4: the project template's deck build (deck/build.py) and its job tools; seam 5: its Beamer deck compiles
with real LaTeX. All on copies of the template filled by fill_template, in temp folders whose names have spaces and
accents."""
import base64
import json
import re
import subprocess
import sys
import tempfile
import time
import zipfile
from html.parser import HTMLParser
from pathlib import Path

import pymupdf
import pytest

from deck_studio.beamer import engine
from deck_studio.core.source_edit import locate_element
from deck_studio.templates import fill_template
from tests.helpers.kit_copy import remove_tree

NAME = "Análise & Cia: 100% {x}"  # every character that breaks HTML, JSON or TeX when pasted raw
VALUES = {"TITLE": NAME, "LANG": "pt-BR", "LANGUAGE": "Português (Brasil)", "PDF": "context/análise.pdf",
          "SLUG": "analise-cia-100-x"}
SLIDES = "deck/src/slides"
STUDIO_OUT = "deck/build/studio/deck.html"
# CRLF line ends, and an emoji (two UTF-16 units) before a start tag on its line
SAMPLE = ('<section class="slide" id="s02" data-part="Parte">\r\n'
          '<h2 class="title">Título</h2>\r\n'
          '<div class="bd">\r\n'
          '  <ul class="b col-w">\r\n'
          '    <li>😀 <b>um</b></li><li class="f">dois<br>três</li>\r\n'
          '  </ul>\r\n'
          '</div>\r\n'
          '<aside class="notes"><p>p. 3</p></aside>\r\n'
          '</section>\r\n')


@pytest.fixture
def project():
    """A filled copy of the template, removed after the test."""
    tmp = Path(tempfile.mkdtemp(prefix="deck-studio-template-"))
    root = tmp / "Análise & Cia"
    fill_template(root, VALUES)
    yield root
    remove_tree(tmp)


def build(project, *args):
    """deck/build.py as the studio runs it; returns the finished process."""
    return subprocess.run([sys.executable, "-I", "-X", "utf8", "deck/build.py", *args], cwd=project,
                          capture_output=True, text=True, encoding="utf-8")


def built(project, *args):
    r = build(project, *args)
    assert r.returncode == 0, r.stdout + r.stderr
    return r


def read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


class Elements(HTMLParser):
    """(tag, attrs) of every element of an HTML text, in order."""

    def __init__(self, text):
        super().__init__()
        self.all = []
        self.feed(text)
        self.close()

    def handle_starttag(self, tag, attrs):
        self.all.append((tag, dict(attrs)))


def located(html):
    return [(tag, attrs) for tag, attrs in Elements(html).all if "data-loc" in attrs]


def test_every_data_loc_of_the_studio_build_resolves_to_its_source_element(project):
    write(project / SLIDES / "02-sample.html", SAMPLE)
    built(project, "--studio")

    out = located(read(project / STUDIO_OUT))
    wrong = []
    for tag, attrs in out:
        file, line, col = re.fullmatch(r"(deck/src/slides/[^/:]+\.html):(\d+):(\d+)", attrs["data-loc"]).groups()
        el = locate_element(read(project / file), int(line), int(col))
        if el is None or el.tag != tag or el.attrs != {k: v or "" for k, v in attrs.items() if k != "data-loc"}:
            wrong.append(attrs["data-loc"])
    assert wrong == []
    # parse5 numbering: 1-based lines (a CRLF is one break) and columns in UTF-16 units
    assert [(tag, attrs["data-loc"].split("/")[-1]) for tag, attrs in out if "02-sample" in attrs["data-loc"]] == [
        ("section", "02-sample.html:1:1"), ("h2", "02-sample.html:2:1"), ("div", "02-sample.html:3:1"),
        ("ul", "02-sample.html:4:3"), ("li", "02-sample.html:5:5"), ("b", "02-sample.html:5:12"),
        ("li", "02-sample.html:5:26"), ("br", "02-sample.html:5:44"), ("aside", "02-sample.html:8:1"),
        ("p", "02-sample.html:8:22")]
    # the title slide that the template brings is located too
    assert ("section", "deck/src/slides/00-title.html:") in {(t, a["data-loc"][:30]) for t, a in out}


class Texts(HTMLParser):
    """The text of each <title> and h2 of an HTML text."""

    def __init__(self, text):
        super().__init__()
        self.texts, self.open = [], None
        self.feed(text)
        self.close()

    def handle_starttag(self, tag, attrs):
        if tag in ("title", "h2"):
            self.open = [tag, ""]
            self.texts.append(self.open)

    def handle_data(self, data):
        if self.open:
            self.open[1] += data

    def handle_endtag(self, tag):
        self.open = None


PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="  # 1x1


@pytest.mark.parametrize("args", [(), ("--studio",)], ids=["clean", "studio"])
def test_an_image_in_img_is_inlined_and_a_name_that_leaves_img_fails_the_build(project, args):
    (project / "deck/src/img/ponto.png").write_bytes(base64.b64decode(PNG))
    (project / "deck/secret.png").write_bytes(base64.b64decode(PNG))  # in deck/, outside deck/src/img
    slide = project / SLIDES / "02-sample.html"
    write(slide, SAMPLE.replace("</aside>", '</aside><img src="img/ponto.png" alt="">'))
    built(project, *args)
    out = project / (STUDIO_OUT if args else "deck/dist/deck.html")
    assert f'src="data:image/png;base64,{PNG}"' in read(out)

    for escape in ("img/../../secret.png", "img/%2e%2e/%2e%2e/secret.png"):
        write(slide, SAMPLE.replace("</aside>", f"</aside><img src='{escape}' alt=''>"))
        r = build(project, *args)
        assert r.returncode != 0 and escape in r.stdout + r.stderr, escape


@pytest.mark.parametrize("args", [(), ("--studio",)], ids=["clean", "studio"])
def test_a_slide_without_an_id_or_with_the_id_of_another_slide_fails_the_build(project, args):
    slide = project / SLIDES / "02-sample.html"
    write(slide, SAMPLE.replace('id="s02"', 'id="s01"'))  # 00-title.html has s01
    r = build(project, *args)
    assert r.returncode != 0 and "s01" in r.stdout + r.stderr

    write(slide, SAMPLE.replace(' id="s02"', ""))
    r = build(project, *args)
    assert r.returncode != 0 and "02-sample.html" in r.stdout + r.stderr


def test_the_studio_deck_runs_under_the_csp_of_its_csp_json_and_a_script_in_a_slide_does_not(project, page):
    for name in ("engine.js", "shell.html"):  # CRLF sources: the browser hashes a script's text with LF line ends
        src = project / "deck/src" / name
        write(src, read(src).replace("\r\n", "\n").replace("\n", "\r\n"))
    write(project / SLIDES / "02-sample.html", SAMPLE.replace("</aside>", "</aside><script>window.fromSlide = 1</script>"))
    built(project, "--studio")

    hashes = json.loads(read(project / "deck/build/studio/csp.json"))["scripts"]
    csp = f"script-src {' '.join(hashes)}; object-src 'none'; base-uri 'none'"
    html = read(project / STUDIO_OUT)
    page.route("http://deck.test/**", lambda route: route.fulfill(
        body=html, content_type="text/html; charset=utf-8", headers={"Content-Security-Policy": csp}))
    page.goto("http://deck.test/deck")
    page.wait_for_function("window.deck", timeout=5000)
    assert page.evaluate("window.deck.state()")["total"] == 2
    assert page.evaluate("window.fromSlide") is None


def test_forty_slides_build_for_the_studio_in_under_a_second(project):
    (project / "deck/src/img/ponto.png").write_bytes(base64.b64decode(PNG))
    slide = SAMPLE.replace("</aside>", '</aside><img src="img/ponto.png" alt="">')
    for part in range(1, 9):  # 1 title slide + 8 files of 5 slides, as a long talk has them
        write(project / SLIDES / f"{part:02d}-parte.html", "".join(slide.replace('"s02"', f'"s{part}-{k}"') for k in range(5)))

    def seconds():
        t = time.perf_counter()
        built(project, "--studio")
        return time.perf_counter() - t

    best = min(seconds() for _ in range(3))  # the first run also warms the disk caches
    assert len(re.findall(r'<section [^>]*class="slide', read(project / STUDIO_OUT))) == 41
    assert best < 1, f"{best:.2f} s"


def test_the_clean_build_has_no_data_loc_and_shows_the_project_name_as_given(project):
    write(project / SLIDES / "02-sample.html", SAMPLE)
    built(project)

    html = read(project / "deck/dist/deck.html")
    assert "data-loc" not in html
    assert html.count('<section class="slide') == 2
    assert [text for _, text in Texts(html).texts] == [NAME, NAME, "Título", "Teclas"]  # <title>, two h2, help
    assert not (project / STUDIO_OUT).exists()


def job(project, script):
    """A job's tool as the studio runs it (generic_config's jobs); returns the finished process."""
    r = subprocess.run([sys.executable, "-I", "-u", script], cwd=project, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")  # as the studio reads a job's output
    assert r.returncode == 0, r.stdout + r.stderr
    return r


def test_the_export_pdf_job_prints_each_slide_on_a_page_of_its_own(project):
    write(project / SLIDES / "02-sample.html", SAMPLE)
    built(project)  # the job's first command
    job(project, "deck/tools/export_pdf.py")

    with pymupdf.open(project / "deck/dist/deck.pdf") as pdf:
        assert pdf.page_count == 2
        assert (round(pdf[0].rect.width), round(pdf[0].rect.height)) == (1200, 675)  # 1600 x 900 px
        assert NAME in " ".join(pdf[0].get_text().split())
        assert "Título" in pdf[1].get_text() and "dois" in pdf[1].get_text()  # its fragment shown


def test_the_overleaf_job_zips_the_beamer_deck_without_its_build_files(project):
    beamer = project / "beamer/apresentacao"
    (beamer / "figures/p003-1.png").write_bytes(base64.b64decode(PNG))
    for name in ("apresentacao.aux", "apresentacao.log", "apresentacao.pdf", "apresentacao.synctex.gz"):
        (beamer / name).write_bytes(b"x")
    r = job(project, "tools/overleaf_zip.py")

    # the job's log (Tarefas) names the zip by its whole path, accents included, with the slug as fill_template wrote it
    assert str((project / "exports" / "analise-cia-100-x-overleaf.zip").resolve()) in r.stdout
    with zipfile.ZipFile(project / "exports/analise-cia-100-x-overleaf.zip") as z:
        assert sorted(z.namelist()) == ["apresentacao.tex", "figures/p003-1.png", "latexmkrc"]
        assert z.read("apresentacao.tex") == (beamer / "apresentacao.tex").read_bytes()


# the front matter's placeholders, which the deck shows until the agent fills them in
PLACEHOLDERS = {"pt-BR": ["[autor]", "[instituição]", "[evento e data]"],
                "en": ["[author]", "[institution]", "[event and date]"]}


@pytest.mark.parametrize("lang", ["pt-BR", "en"])
def test_the_filled_beamer_deck_compiles_with_pdflatex_without_errors(lang):
    """Seam 5: real latexmk, as the studio compiles (-norc, no shell escape), into a temp folder. Its words, the
    placeholders of the title page included, are in the slides' language."""
    tmp = Path(tempfile.mkdtemp(prefix="deck-studio-template-"))
    try:
        project = fill_template(tmp / "Análise & Cia", {**VALUES, "LANG": lang})
        main = project / "beamer/apresentacao/apresentacao.tex"
        result = engine.compile({"kind": "handwritten", "main": str(main)}, tmp / "saída latex")

        assert result["ok"] and result["errors"] == [], result
        assert result["engine"] == "pdflatex"
        with pymupdf.open(result["pdf"]) as pdf:
            assert pdf.page_count == 2  # the title and the outline
            title = " ".join(pdf[0].get_text().split())
            assert NAME in title
            assert [w for w in PLACEHOLDERS["pt-BR"] + PLACEHOLDERS["en"] if w in title] == PLACEHOLDERS[lang]
            assert ("Sumário" if lang == "pt-BR" else "Contents") in pdf[1].get_text()
        assert sorted(p.name for p in main.parent.iterdir()) == ["apresentacao.tex", "figures", "latexmkrc"]
    finally:
        remove_tree(tmp)


def test_the_studio_build_leaves_what_a_browser_shows_as_text_as_it_is(project):
    """A browser shows the content of textarea, xmp and plaintext as text: a data-loc there would show on the slide."""
    raw = "<textarea><p>exemplo</p></textarea><xmp><b>x</b></xmp>"
    write(project / SLIDES / "02-sample.html", SAMPLE.replace("</aside>", "</aside>" + raw))
    built(project, "--studio")
    assert raw in read(project / STUDIO_OUT)


OUTSIDE = """() => {  // each element of each slide, at its last step, that leaves its slide's frame
  const out = [], steps = window.deck.steps();
  document.querySelectorAll('#stage section.slide').forEach((slide, i) => {
    window.deck.go(i + 1, steps[i]);
    const frame = slide.getBoundingClientRect();
    for (const el of slide.querySelectorAll('*')) {
      const r = el.getBoundingClientRect();
      if (el.closest('aside.notes') || !(r.width || r.height)) continue;
      if (r.top < frame.top - 1 || r.bottom > frame.bottom + 1 || r.left < frame.left - 1 || r.right > frame.right + 1)
        out.push(`${slide.id} ${el.tagName.toLowerCase()}.${el.className}`);
    }
  });
  return out;
}"""


def test_every_example_slide_fits_its_slide_an_articles_long_title_included(project, page):
    """The agent copies each slide from an example of exemplos/ (one per type, from the NEXUS-GO kit), and an
    article's full title, as the PDF has it, goes in the title slide's subtitle."""
    examples = sorted((project / ".claude/skills/criar-apresentacao/exemplos").glob("*.html"))
    assert len(examples) == 18
    patterns = "\n".join(read(f) for f in examples)
    long_title = ("Network-Extended Unified Sequence Embeddings for Gene Ontology Function Annotation in Large Protein "
                  "Interaction Graphs")
    assert len(long_title) >= 117
    patterns = patterns.replace("[Título completo do trabalho, como a fonte o escreve]", long_title)
    (project / SLIDES / "00-title.html").unlink()
    write(project / SLIDES / "01-padroes.html", patterns)
    figure = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 1200, 800), False)
    figure.clear_with(200)
    (project / "deck/src/img/exemplo-figura.png").write_bytes(figure.tobytes("png"))
    built(project)

    html = read(project / "deck/dist/deck.html")
    page.set_viewport_size({"width": 1600, "height": 900})
    page.emulate_media(reduced_motion="reduce")
    page.route("http://deck.test/**", lambda route: route.fulfill(body=html, content_type="text/html; charset=utf-8"))
    page.goto("http://deck.test/deck")
    page.wait_for_function("window.deck", timeout=5000)
    assert page.evaluate(OUTSIDE) == []


def test_an_english_deck_has_its_help_notes_and_presenter_words_in_english():
    tmp = Path(tempfile.mkdtemp(prefix="deck-studio-template-"))
    try:
        project = fill_template(tmp / "Talk", {**VALUES, "LANG": "en", "LANGUAGE": "English"})
        built(project)
        html = read(project / "deck/dist/deck.html")
        assert [text for tag, text in Texts(html).texts if tag == "h2"][-1] == "Keys"  # the help's heading
        for words in ("Close notes", "next step or slide", ">Next<", "step ${frag} of", "<title>Presenter</title>"):
            assert words in html, words
        for words in ("Fechar", "Teclas", "Próximo", "passo ${", "Apresentador", "Diferença", ">rota<"):
            assert words not in html, words
    finally:
        remove_tree(tmp)
