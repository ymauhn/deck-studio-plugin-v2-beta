"""SPEC story 53 on the adapter's own job lists: exports and publishing start from the clean build, so what leaves the
studio carries no studio markers. (Other studios run stand-ins for every job.) In this kit copy the exporter is a
stand-in that reports what it was given, and the publish script is deleted, so nothing can reach Netlify."""
import json

from deck_studio.config import nexus_go_config
from tests.e2e.conftest import open_studio, run_studio
from tests.e2e.test_jobs import run_in_page
from tests.helpers.kit_copy import make_kit_copy, remove_kit_copy

# the exporter's stand-in: it reads the deck the real one prints and says how many studio markers that deck holds
EXPORTER = """import pathlib
deck = pathlib.Path('deck', 'dist', 'nexus-go-defense.html').read_text(encoding='utf-8')
pathlib.Path('deck', 'dist', 'nexus-go-defense.pdf').write_bytes(b'%PDF-1.4 stand-in')
print('exported', deck.count(' data-loc='), 'studio markers')
"""


def logged(run):
    """The commands a job ran ("> ..." lines) and the lines they printed."""
    lines = [e["line"] for e in run["events"] if "line" in e]
    return [line for line in lines if line.startswith("> ")], [line for line in lines if not line.startswith("> ")]


def test_exportar_pdf_and_publicar_start_from_the_clean_build_so_their_deck_has_no_studio_markers(page, tmp_path):
    kit = make_kit_copy()
    try:
        jobs = {name: nexus_go_config(kit)["jobs"][name] for name in ("export-pdf", "publish")}  # the adapter's own
        assert jobs["publish"][-1][-2:] == ["-File", "deck/tools/publish_netlify.ps1"]  # the script deleted here
        (kit / "deck/tools/publish_netlify.ps1").unlink()
        (kit / "deck/tools/export_pdf.py").write_text(EXPORTER, encoding="utf-8")
        config = tmp_path / "config.json"
        config.write_text(json.dumps({"jobs": jobs}), encoding="utf-8")
        with run_studio("--config", config, kit=kit) as studio:
            open_studio(page, studio)
            export = run_in_page(page, "export-pdf")
            commands, printed = logged(export)
            assert commands == ["> node deck/build.mjs", "> python -I -u deck/tools/export_pdf.py"]
            assert "exported 0 studio markers" in printed
            assert export["events"][-1]["state"] == "ok"

            dist = kit / "deck/dist/nexus-go-defense.html"
            dist.write_bytes((kit / "deck/build/studio/nexus-go-defense.html").read_bytes())  # a studio deck there
            run = run_in_page(page, "publish", {"confirm": True})
            commands, _ = logged(run)
            assert commands == ["> node deck/build.mjs",
                                "> powershell -NoProfile -ExecutionPolicy Bypass -File deck/tools/publish_netlify.ps1"]
            assert run["events"][-1]["state"] == "error"  # its script is gone
            assert b" data-loc=" not in dist.read_bytes()  # what the script would have sent is the clean deck again
    finally:
        remove_kit_copy(kit)
