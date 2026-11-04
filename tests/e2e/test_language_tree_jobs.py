"""The Portuguese tree and the jobs, images and publishing (review of PR #3, 2026-11-04): the language does not change
under a running job; an image added with PT on screen goes to deck/src-pt/img; Publicar says it updates / and /pt."""
import json
import struct
import sys
import zlib

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import built, wait_until

SLOW_EXPORT = [[sys.executable, "-c", "import time; time.sleep(4); print('stand-in for the export-pdf job')"]]


@pytest.fixture(scope="module")
def studio_args(tmp_path_factory):
    config = tmp_path_factory.mktemp("cfg") / "config.json"
    config.write_text(json.dumps({"jobs": {"export-pdf": SLOW_EXPORT}}), encoding="utf-8")
    return ["--config", config]


def png(path):
    """A 1×1 PNG."""
    chunk = lambda kind, data: (struct.pack(">I", len(data)) + kind + data  # noqa: E731
                                + struct.pack(">I", zlib.crc32(kind + data)))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")) + chunk(b"IEND", b""))


def switch_to(studio, api, lang):
    return api.post(f"{studio.base}/api/language", headers=studio.headers, data={"lang": lang})


def jobs_running(studio, api):
    return api.get(f"{studio.base}/api/status", headers=studio.headers).json()


def test_the_language_does_not_change_while_a_job_runs(studio, studio_page, api):
    page = studio_page
    r = api.post(f"{studio.base}/api/jobs/export-pdf", headers=studio.headers, data={})
    assert r.status == 202
    refused = switch_to(studio, api, "pt")
    assert refused.status == 409 and "tarefa" in refused.json()["message"]
    wait_until(lambda: switch_to(studio, api, "pt").status == 200, 20, "the job to end and the switch to go through")
    built(studio, api)
    expect(page.get_by_role("radiogroup", name="Idioma do deck").get_by_role("radio", name="Português")).to_have_attribute(
        "aria-checked", "true")


def test_an_image_added_in_pt_goes_to_the_portuguese_tree(studio, studio_page, api):
    page = studio_page
    png(studio.kit / "context" / "figura-pt.png") if (studio.kit / "context").is_dir() else (
        (studio.kit / "context").mkdir(), png(studio.kit / "context" / "figura-pt.png"))
    assert json.loads((studio.data / "settings.json").read_text(encoding="utf-8"))["language"] == "pt"
    page.get_by_role("textbox", name="Mensagem").fill("#scenario:add-image-pt")
    page.get_by_role("textbox", name="Mensagem").press("Enter")
    answer = page.get_by_role("log", name="Conversa").get_by_role("article", name="Claude").last
    expect(answer).to_contain_text("Copied to deck/src-pt/img/figura-pt.png")
    expect(answer).to_contain_text('<img src="img/figura-pt.png"')
    assert (studio.kit / "deck" / "src-pt" / "img" / "figura-pt.png").is_file()
    assert not (studio.kit / "deck" / "src" / "img" / "figura-pt.png").exists()
    files = page.get_by_role("region", name="Arquivos")
    expect(files).to_contain_text("deck/src-pt/img/")


def test_publicar_says_it_updates_both_decks(studio, studio_page, api):
    page = studio_page
    assert api.get(f"{studio.base}/api/jobs/site", headers=studio.headers).json()["paths"] == ["/", "/pt"]
    page.get_by_role("button", name="Publicar").click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_contain_text("As duas versões vão juntas: / e /pt.")
    dialog.get_by_role("button", name="Cancelar").click()
    expect(dialog).to_be_hidden()
