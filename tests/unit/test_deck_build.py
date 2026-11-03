"""Seam 4: the kit's deck build (clean, --studio and --part) and the studio deck's in-place swap, on kit copies."""
import base64
import hashlib
import json
import re
import shutil
import subprocess
import time
from collections import namedtuple
from html.parser import HTMLParser
from pathlib import Path

import pytest
from playwright.sync_api import expect

from tests.helpers.kit_copy import make_kit_copy, remove_kit_copy

ORIG_BUILD = Path(__file__).resolve().parents[1] / "fixtures" / "build.orig.mjs"
CLEAN_OUT = "deck/dist/nexus-go-defense.html"
STUDIO_OUT = "deck/build/studio/nexus-go-defense.html"
SLIDES = "deck/src/slides"
NODE = shutil.which("node")


def build(kit, *args):
    r = subprocess.run([NODE, *args], cwd=kit, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


El = namedtuple("El", "tag attrs parent loc")  # parent: the attributes of the enclosing element
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class Elements(HTMLParser):
    """Every element of an HTML text, in order; loc is its start tag's 'line:col' (1-based, as parse5 gives it)."""

    def __init__(self, text):
        super().__init__()
        self.all, self.open = [], []
        self.feed(text)
        self.close()

    def handle_startendtag(self, tag, attrs):
        line, offset = self.getpos()
        self.all.append(El(tag, dict(attrs), self.open[-1][1] if self.open else {}, f"{line}:{offset + 1}"))

    def handle_starttag(self, tag, attrs):
        self.handle_startendtag(tag, attrs)
        if tag not in VOID:
            self.open.append((tag, self.all[-1].attrs))

    def handle_endtag(self, tag):
        for i in range(len(self.open) - 1, -1, -1):
            if self.open[i][0] == tag:
                del self.open[i:]
                return


def classes(el):
    return (el.attrs.get("class") or "").split()


def test_clean_build_is_byte_identical_to_the_pre_studio_build_script(kit_copy):
    shutil.copyfile(ORIG_BUILD, kit_copy / "deck" / "build.orig.mjs")
    build(kit_copy, "deck/build.orig.mjs")
    out = kit_copy / CLEAN_OUT
    before = hashlib.sha256(out.read_bytes()).hexdigest()
    out.unlink()
    build(kit_copy, "deck/build.mjs")
    assert hashlib.sha256(out.read_bytes()).hexdigest() == before


def matches_source(el, src):
    """What the source element at an output element's data-loc must be: the build turns span.m into
    mjx-container, div.m.d into div.eq and a data-table placeholder into div.tbl."""
    if el.tag == "mjx-container":
        return src.tag == "span" and src.attrs.get("class") == "m"
    if el.tag == "div" and el.attrs.get("class") == "eq":
        return src.tag == "div" and src.attrs.get("class") == "m d"
    placeholder = el.tag == "div" and "tbl" in classes(el)
    return (src.tag == el.tag and src.attrs.get("class") == el.attrs.get("class")
            and (not placeholder or "data-table" in src.attrs))


def test_every_data_loc_in_the_studio_build_resolves_to_its_source_element(kit_copy):
    build(kit_copy, "deck/build.mjs", "--studio")
    located = [el for el in Elements(read(kit_copy / STUDIO_OUT)).all if "data-loc" in el.attrs]
    sources, wrong = {}, []
    for el in located:
        m = re.fullmatch(r"(deck/src/slides/[^/:]+\.html):(\d+):(\d+)", el.attrs["data-loc"])
        if m and m[1] not in sources:
            sources[m[1]] = {s.loc: s for s in Elements(read(kit_copy / m[1])).all}
        src = m and sources[m[1]].get(f"{m[2]}:{m[3]}")
        if not src or not matches_source(el, src):
            wrong.append(f"{el.attrs['data-loc']} {el.tag}.{'.'.join(classes(el))}")
    assert wrong == []
    assert len(located) > 1000, f"only {len(located)} elements carry a data-loc"


def test_studio_build_keeps_every_equation_and_table_with_their_locations(kit_copy):
    count = lambda text, pattern: len(re.findall(pattern, text))  # noqa: E731
    build(kit_copy, "deck/build.mjs")
    equations = count(read(kit_copy / CLEAN_OUT), r"<mjx-container[\s>]")
    build(kit_copy, "deck/build.mjs", "--studio")
    studio = read(kit_copy / STUDIO_OUT)

    assert '<span class="m"' not in studio, "raw inline math left in the studio build"
    assert '<div class="m d"' not in studio, "raw display math left in the studio build"
    assert equations > 0
    assert count(studio, r"<mjx-container[\s>]") == equations

    placeholders = sum(read(f).count('data-table="') for f in (kit_copy / SLIDES).glob("*.html"))
    every = Elements(studio).all
    assert len([el for el in every if el.tag == "table" and "t" in classes(el)]) == placeholders
    assert len([el for el in every if el.tag == "div" and "tbl" in classes(el)]) == placeholders
    # generated nodes keep their placeholder's data-loc: div.tbl, div.eq and inline mjx-container
    generated = lambda el: (el.tag == "div" and ("tbl" in classes(el) or el.attrs.get("class") == "eq")  # noqa: E731
                            or el.tag == "mjx-container" and el.parent.get("class") != "eq")
    assert [el.tag for el in every if generated(el) and "data-loc" not in el.attrs] == []


def test_a_user_image_in_deck_src_img_is_inlined_by_both_builds(kit_copy):
    png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="  # 1x1 PNG
    img = kit_copy / "deck" / "src" / "img"
    img.mkdir(parents=True, exist_ok=True)
    (img / "studio-test-dot.png").write_bytes(base64.b64decode(png))
    part = sorted((kit_copy / SLIDES).glob("*.html"))[0]
    src = read(part)
    assert "</section>" in src, f"no slide in {part}"
    write(part, src.replace("</section>", '<img src="img/studio-test-dot.png" alt=""></section>', 1))

    build(kit_copy, "deck/build.mjs")
    build(kit_copy, "deck/build.mjs", "--studio")
    inlined = f'src="data:image/png;base64,{png}"'
    assert inlined in read(kit_copy / CLEAN_OUT), "not inlined by the clean build"
    assert inlined in read(kit_copy / STUDIO_OUT), "not inlined by the studio build"


def sections(html):
    """id -> outerHTML of every slide section of a built deck, in deck order."""
    stage = html[html.index('<div id="stage">'):html.index('<div id="chrome"')]
    out, depth = {}, 0
    for m in re.finditer(r"<section\b[^>]*>|</section>", stage):
        if m[0] == "</section>":
            depth -= 1
            if depth == 0:
                out[sid] = stage[start:m.end()]
        else:
            if depth == 0:
                start, sid = m.start(), re.search(r'\bid="([^"]*)"', m[0])[1]
            depth += 1
    return out


def part_build(kit, part):
    build(kit, "deck/build.mjs", "--studio", "--part", part)
    return json.loads(read(kit / "deck" / "build" / "studio" / "parts" / f"{part}.json"))


def test_a_part_build_gives_each_section_exactly_as_the_full_studio_build_does(kit_copy):
    build(kit_copy, "deck/build.mjs", "--studio")
    full = sections(read(kit_copy / STUDIO_OUT))
    seen = []
    for f in sorted((kit_copy / SLIDES).glob("*.html")):
        part = part_build(kit_copy, f.name)
        assert part["part"] == f.name
        assert [s["html"] for s in part["slides"]] == [full[s["id"]] for s in part["slides"]], f.name
        seen += [s["id"] for s in part["slides"]]
    assert seen == list(full)


def test_a_part_build_is_clearly_faster_than_a_full_studio_build(kit_copy):
    def best(*args):  # the fastest of three runs: the first one also warms the copy's caches
        times = []
        for _ in range(3):
            t = time.perf_counter()
            build(kit_copy, "deck/build.mjs", "--studio", *args)
            times.append(time.perf_counter() - t)
        return min(times)

    full, part = best(), best("--part", "04-method.html")
    assert part < 0.75 * full, f"part build {part:.3f} s, full studio build {full:.3f} s"


@pytest.fixture(scope="module")
def studio_kit():
    """One kit copy with a full studio build for the swap tests; each test edits a part file of its own."""
    kit = make_kit_copy()
    try:
        build(kit, "deck/build.mjs", "--studio")
        yield kit
    finally:
        remove_kit_copy(kit)


@pytest.fixture
def deck(page, studio_kit):
    """The copy's studio deck, offline (the Google Fonts link fails at once)."""
    page.route(re.compile(r"^https?://"), lambda route: route.abort())
    page.goto((studio_kit / STUDIO_OUT).as_uri())
    page.wait_for_function("window.deck")
    return page


def swap(page, kit, part):
    p = part_build(kit, part)
    return page.evaluate("p => window.__studio.swap(p.slides, p.css)", p)


def go_to(page, selector, step):
    """Shows the slide that holds `selector` at `step`, and returns the deck state."""
    return page.evaluate("""([selector, step]) => {
      const slides = [...document.querySelectorAll('section.slide')];
      window.deck.go(slides.indexOf(document.querySelector(selector).closest('section.slide')) + 1, step);
      return window.deck.state();
    }""", [selector, step])


def test_a_swap_shows_an_edited_slide_on_the_same_slide_and_step_without_a_reload(deck, studio_kit):
    old, new = "test read once", "test read exactly once"
    part = studio_kit / SLIDES / "03-data.html"
    src = read(part)
    assert src.count(old) == 1 and src.count("</style>") == 1
    before = go_to(deck, "#s17", 2)
    deck.evaluate("window.marker = 'no reload'; window.replaced = document.querySelector('section.slide.active')")
    write(part, src.replace(old, new).replace("</style>", "#s17 li { color: rgb(1, 2, 3); }\n</style>"))

    assert swap(deck, studio_kit, "03-data.html") is True
    assert deck.evaluate("window.marker") == "no reload"
    assert deck.evaluate("window.deck.state()") == before
    bullet = deck.locator("section.slide.active li", has_text=new)
    expect(bullet).to_have_class(re.compile(r"\bon\b"))  # its fragment, step 2, is shown
    expect(bullet).to_have_css("color", "rgb(1, 2, 3)")  # and the part's new CSS applies
    expect(deck.locator("section.slide.active", has_text=old)).to_have_count(0)
    # the keys drive only the new engine: the old one would take 'active' off the section it showed
    deck.keyboard.press("End")
    assert deck.evaluate("window.deck.state().slide === window.deck.state().total")
    assert deck.evaluate("window.replaced.classList.contains('active')")


def test_a_swapped_slide_renders_its_component_again(deck, studio_kit):
    go_to(deck, '[data-component="INT-GAP"]', 2)
    deck.evaluate("document.querySelector('[data-component=\"INT-GAP\"]').before = true")

    assert swap(deck, studio_kit, "01-motivation.html") is True
    gap = deck.locator('section.slide.active [data-component="INT-GAP"]')
    assert gap.evaluate("el => el.before") is None  # a new element,
    expect(gap.locator(":scope > *")).not_to_have_count(0)  # rendered by its component
    assert deck.evaluate("window.deck.component('INT-GAP') !== null")


def test_a_swap_without_css_keeps_the_part_css(deck, studio_kit):
    go_to(deck, ".s24-left", 0)
    p = part_build(studio_kit, "04-method.html")

    assert deck.evaluate("slides => window.__studio.swap(slides)", p["slides"]) is True
    expect(deck.locator("section.slide.active .s24-left")).to_have_css("row-gap", "34px")  # 04-method.html's CSS


def test_listeners_that_deck_features_add_during_a_swap_outlive_the_next_swap(deck, studio_kit):
    deck.evaluate("""() => document.addEventListener('deck:change', () => {
      if (window.pings === undefined) { window.pings = 0; addEventListener('feature-ping', () => window.pings++); }
    })""")
    p = part_build(studio_kit, "06-conclusions.html")
    for _ in range(2):
        assert deck.evaluate("p => window.__studio.swap(p.slides, p.css)", p) is True

    deck.evaluate("dispatchEvent(new Event('feature-ping'))")
    assert deck.evaluate("window.pings") == 1


def test_a_part_whose_slides_changed_cannot_be_swapped(deck, studio_kit):
    part = studio_kit / SLIDES / "00-opening.html"
    src = read(part)
    write(part, src[:src.index('<section class="slide" id="s02"')])  # the roadmap slide is gone

    assert swap(deck, studio_kit, "00-opening.html") is False
    expect(deck.locator("#s02")).to_have_count(1)


def test_an_image_path_that_leaves_the_image_folders_fails_both_builds(kit_copy):
    (kit_copy / "deck" / "secret.png").write_bytes(b"\x89PNG not a deck image")  # in deck/, outside img/ and svg/
    slide = kit_copy / SLIDES / "03-data.html"
    write(slide, read(slide).replace("</section>", '<img src="img/../../secret.png" alt=""></section>', 1))
    for args in (["deck/build.mjs"], ["deck/build.mjs", "--studio"]):
        r = subprocess.run([NODE, *args], cwd=kit_copy, capture_output=True, text=True, encoding="utf-8")
        assert r.returncode != 0, args
        assert "img/../../secret.png" in r.stdout + r.stderr, args
