"""NEXUS-GO's adapter as load_config builds it from the real kit (review of PR #3, 2026-11-04): the export and publish
command lists in English and with the Portuguese tree, and the write guard on the files the studio runs."""
import pytest

from deck_studio.config import EXPORT_PT, load_config
from deck_studio.core.write_guard import LEVELS, create_guard
from tests.helpers.kit_copy import REAL_KIT

CLEAN = ["node", "deck/build.mjs"]
CLEAN_PT = ["node", "deck/build.mjs", "--pt"]
PUBLISH = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "deck/tools/publish_netlify.ps1"]

pytestmark = pytest.mark.skipif(not (REAL_KIT / "deck" / "src-pt" / "slides").is_dir(),
                                reason="the real kit with deck/src-pt is not on this machine")


@pytest.fixture(scope="module")
def config():
    return load_config(REAL_KIT)


def test_export_follows_the_language_on_screen(config):
    assert config["jobs"]["export-pdf"] == [CLEAN, ["python", "-I", "-u", "deck/tools/export_pdf.py"]]
    assert config["jobOutputs"]["export-pdf"] == "deck/dist/nexus-go-defense.pdf"
    pt = config["languageTrees"]["pt"]
    assert pt["jobs"]["export-pdf"] == [CLEAN_PT, ["python", "-I", "-u", "-c", EXPORT_PT]]
    assert pt["jobOutputs"]["export-pdf"] == "deck/dist/nexus-go-defesa-pt.pdf"


def test_publish_builds_both_decks_in_either_language_and_says_so(config):
    """publish_netlify.ps1 uploads whatever deck/dist/nexus-go-defesa-pt.html holds to /pt: an old one went up with
    EN on screen."""
    assert config["jobs"]["publish"] == [CLEAN, CLEAN_PT, PUBLISH]
    assert config["languageTrees"]["pt"]["jobs"]["publish"] == [CLEAN, CLEAN_PT, PUBLISH]
    assert config["publishPaths"] == ["/", "/pt"]


def test_every_clean_build_takes_the_build_lock_in_either_language(config):
    assert config["cleanBuild"] == CLEAN and config["otherCleanBuilds"] == [CLEAN_PT]
    pt = config["languageTrees"]["pt"]
    assert pt["cleanBuild"] == CLEAN_PT and pt["otherCleanBuilds"] == [CLEAN]


def test_the_portuguese_tree_has_its_own_slides_and_images(config):
    pt = config["languageTrees"]["pt"]
    assert pt["slidesDir"] == "deck/src-pt/slides"
    assert pt["imagesDir"] == "deck/src-pt/img"
    assert pt["studioBuild"][-1] == "--pt" and "--pt" in pt["partBuild"]


@pytest.mark.parametrize("level", LEVELS)
def test_what_the_studio_runs_never_changes_without_the_author(config, level):
    guard = create_guard(config)
    kit = config["kitRoot"]

    def write(rel):
        return guard.check("Write", {"file_path": f"{kit}\\{rel}", "content": "x"}, level).behavior

    for rel in ["deck\\build.mjs", "deck\\package.json", "deck\\tools\\export_pdf.py",
                "deck\\tools\\publish_netlify.ps1", "deck\\tools\\netlify-site.json", "tools\\extract_tables.py",
                "beamer\\tools\\build.py", ".claude\\settings.json", ".claude\\settings.local.json", "CLAUDE.md",
                "video\\CLAUDE.md", "deck\\src\\engine.js", "deck\\src-pt\\shell.html"]:
        assert write(rel) == "ask", (level, rel)
    assert write("deck\\node_modules\\esbuild\\install.js") == "deny"
    assert write("deck\\src-pt\\slides\\00-opening.html") == ("ask" if level == "ask" else "allow")
    assert write("deck\\src-pt\\img\\nova.png") == ("ask" if level == "ask" else "allow")


def test_the_origem_reads_the_slides_on_screen():
    """With PT on screen, the number index comes from deck/src-pt/slides (review of PR #3)."""
    from deck_studio.provenance import build_index
    from tests.helpers.kit_copy import make_kit_copy, remove_kit_copy

    kit = make_kit_copy()
    try:
        pt = build_index(kit, "deck/src-pt/slides")["slides"]
        en = build_index(kit)["slides"]
        assert pt and set(pt) == set(en)  # the same slide ids, read from the other tree
        (kit / "deck" / "src-pt" / "slides" / "00-opening.html").write_text(
            '<section class="slide" id="s01"><h2 class="title">X</h2><p>987654</p></section>', encoding="utf-8")
        assert "987654" in [e["number"] for e in build_index(kit, "deck/src-pt/slides")["slides"]["s01"]]
        assert "987654" not in [e["number"] for e in build_index(kit)["slides"].get("s01", [])]
    finally:
        remove_kit_copy(kit)
