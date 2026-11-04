"""Cadastrar link de publicação (pedido de 04/11/2026): a project registers a Netlify site, then Publicar runs the
project's deck/tools/publish_netlify.py with the same confirmation as the kit's. Netlify here is a local stand-in
(NETLIFY_API): nothing leaves the machine."""
import http.server
import io
import json
import tempfile
import threading
import zipfile
from pathlib import Path

import pytest
from playwright.sync_api import expect

from deck_studio.templates import fill_template
from tests.e2e.conftest import open_studio, run_studio
from tests.helpers.kit_copy import PREFIX, remove_kit_copy

TITLE = "Projeto de Publicação"


class FakeNetlify(http.server.BaseHTTPRequestHandler):
    sites, deploys, calls = {}, {}, []

    def log_message(self, *a):
        pass

    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.calls.append(("GET", self.path, self.headers.get("Authorization")))
        if self.path.startswith("/api/v1/sites/"):
            name = self.path.rsplit("/", 1)[1].removesuffix(".netlify.app")
            site = next((s for s in self.sites.values() if s["name"] == name), None)
            return self._send(200, site) if site else self._send(404, {"message": "Not Found"})
        if self.path.startswith("/api/v1/deploys/"):
            return self._send(200, {"id": self.path.rsplit("/", 1)[1], "state": "ready"})
        self._send(404, {})

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.calls.append(("POST", self.path, self.headers.get("Authorization")))
        if self.path == "/api/v1/sites":
            name = json.loads(body)["name"]
            site = {"id": f"id-{name}", "name": name, "ssl_url": f"https://{name}.netlify.app"}
            self.sites[site["id"]] = site
            return self._send(201, site)
        if self.path.endswith("/deploys"):
            self.deploys[self.path.split("/")[4]] = body
            return self._send(200, {"id": "d1", "state": "uploaded"})
        self._send(404, {})


@pytest.fixture(scope="module")
def netlify():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeNetlify)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    FakeNetlify.sites["id-existente"] = {"id": "id-existente", "name": "existente",
                                         "ssl_url": "https://existente.netlify.app"}
    yield f"http://127.0.0.1:{server.server_address[1]}/api/v1"
    server.shutdown()


@pytest.fixture(scope="module")
def project(netlify):
    kit = Path(tempfile.mkdtemp(prefix=PREFIX))  # remove_kit_copy deletes it
    try:
        fill_template(kit, {"TITLE": TITLE, "LANG": "pt-BR", "LANGUAGE": "Português (Brasil)",
                            "PDF": "context/artigo.pdf", "SLUG": "projeto-de-publicacao"})
        (kit / "studio.json").write_text(json.dumps({"title": TITLE, "format": "html", "language": "pt"}),
                                         encoding="utf-8")
        with run_studio(kit=kit, env={"NETLIFY_API": netlify, "NETLIFY_AUTH_TOKEN": "token-de-teste"}) as s:
            yield s
    finally:
        remove_kit_copy(kit)


def post(api, studio, data):
    return api.post(f"{studio.base}/api/publish-site", headers=studio.headers, data=data)


def test_the_route_needs_a_name_and_a_confirmation_to_create(project, api):
    assert post(api, project, {"name": ""}).status == 400
    r = post(api, project, {"name": "novo-site", "create": True})
    assert r.status == 400 and "confirmação" in r.json()["message"]
    r = post(api, project, {"name": "nao-existe"})  # an existing site that is not in the account
    assert r.status == 400 and "404" in r.json()["message"]
    assert not (project.kit / "deck/tools/netlify-site.json").exists()


def test_the_nexus_go_studio_does_not_offer_it(studio, api):
    status = api.get(f"{studio.base}/api/status", headers=studio.headers).json()
    assert status["project"]["registerSite"] is False
    assert post(api, studio, {"name": "x"}).status == 400


def test_a_new_site_is_registered_and_then_publicar_publishes_the_deck(project, page, api):
    open_studio(page, project)
    expect(page.get_by_role("button", name="Publicar")).to_have_count(0)
    page.get_by_role("button", name="Cadastrar link de publicação").click()
    dialog = page.get_by_role("dialog", name="Cadastrar link de publicação")
    dialog.get_by_label("Nome do site no Netlify").fill("deck-teste-e2e")
    dialog.get_by_label("criar um site novo com esse nome").check()
    dialog.get_by_role("button", name="Cadastrar").click()
    confirm = page.get_by_role("dialog").filter(has_text="Criar o site deck-teste-e2e.netlify.app")
    confirm.get_by_role("button", name="Confirmar").click()
    expect(page.get_by_role("button", name="Publicar")).to_be_visible(timeout=20_000)  # after the reload
    expect(page.get_by_role("button", name="Cadastrar link de publicação")).to_have_count(0)
    site = json.loads((project.kit / "deck/tools/netlify-site.json").read_text(encoding="utf-8"))
    assert site == {"id": "id-deck-teste-e2e", "name": "deck-teste-e2e", "url": "https://deck-teste-e2e.netlify.app"}
    assert ("POST", "/api/v1/sites", "Bearer token-de-teste") in FakeNetlify.calls

    page.get_by_role("button", name="Publicar").click()
    confirm = page.get_by_role("dialog").filter(has_text="https://deck-teste-e2e.netlify.app")
    confirm.get_by_role("button", name="Confirmar").click()
    # poll with Playwright's own wait: the page fixture routes every request through Python, which a time.sleep loop
    # would block (the POST of the job would hang)
    for _ in range(120):
        if FakeNetlify.deploys.get("id-deck-teste-e2e"):
            break
        page.wait_for_timeout(500)
    zipped = FakeNetlify.deploys["id-deck-teste-e2e"]
    with zipfile.ZipFile(io.BytesIO(zipped)) as z:
        assert sorted(z.namelist()) == ["_headers", "index.html", "robots.txt"]
        assert TITLE in z.read("index.html").decode("utf-8")
        assert "noindex" in z.read("_headers").decode()
    expect(page.locator(".jobs-list")).to_contain_text("ready: https://deck-teste-e2e.netlify.app", timeout=30_000)


def test_an_existing_site_of_the_account_can_be_registered_too(netlify, api):
    kit = Path(tempfile.mkdtemp(prefix=PREFIX))
    try:
        fill_template(kit, {"TITLE": "Outro", "LANG": "pt-BR", "LANGUAGE": "Português (Brasil)",
                            "PDF": "context/a.pdf", "SLUG": "outro"})
        (kit / "studio.json").write_text(json.dumps({"title": "Outro", "format": "html", "language": "pt"}),
                                         encoding="utf-8")
        (kit / "deck/tools/publish_netlify.py").unlink()  # an older project: the studio copies the tool in
        with run_studio(kit=kit, env={"NETLIFY_API": netlify, "NETLIFY_AUTH_TOKEN": "t"}) as s:
            r = post(api, s, {"name": "existente"})
            assert r.status == 200 and r.json()["url"] == "https://existente.netlify.app"
            assert "publish" in r.json()["jobs"]
            assert (kit / "deck/tools/publish_netlify.py").is_file()
            status = api.get(f"{s.base}/api/status", headers=s.headers).json()
            assert status["project"]["registerSite"] is False and "publish" in status["project"]["jobs"]
    finally:
        remove_kit_copy(kit)
