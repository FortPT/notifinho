"""Packaged WebUI, transport, and browser-security contract tests."""

from __future__ import annotations

import http.client
import threading

from html.parser import HTMLParser
from pathlib import Path

import inputs.http as http_module

from dispatcher import Dispatcher
from inputs.http import HTTPServer
from storage.database import Database
from webui.service import SECURITY_HEADERS, WebUIService


ROOT = Path(__file__).resolve().parents[1]


class Configuration:
    def __init__(self, data):
        self.data = data

    def get(self, *keys, default=None):
        value = self.data
        for key in keys:
            if not isinstance(value, dict) or key not in value:
                return default
            value = value[key]
        return value


class Router:
    def route(self, _item):
        raise AssertionError("WebUI assets must not enter notification routing")


class MarkupInspector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.scripts = []
        self.stylesheets = []
        self.inline_handlers = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(values["id"])
        if tag == "script":
            self.scripts.append(values.get("src"))
        if tag == "link" and values.get("rel") == "stylesheet":
            self.stylesheets.append(values.get("href"))
        self.inline_handlers.extend(
            name for name, _value in attrs if name.casefold().startswith("on")
        )


def enabled_config():
    return Configuration({
        "http": {"enabled": True},
        "api": {"enabled": True},
        "platform": {"enabled": True},
        "webui": {"enabled": True},
    })


def http_request(port, method, path):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    connection.request(method, path)
    response = connection.getresponse()
    status = response.status
    headers = response.getheaders()
    body = response.read()
    connection.close()
    return status, headers, body


def test_webui_service_is_explicitly_gated_and_has_no_path_mapping():
    service = WebUIService(enabled_config(), root=ROOT)

    assert service.enabled is True
    assert service.response("/").status == 200
    assert service.response("/ui/app.js").content_type.startswith("text/javascript")
    assert service.response("/ui/styles.css").content_type.startswith("text/css")
    assert service.response("/ui/icon.png").content_type == "image/png"
    assert service.response("/ui/../config/config.yaml").status == 404
    assert service.response("/api/v2/session") is None
    assert service.response("/home-assistant/events") is None

    unavailable = WebUIService(
        enabled_config(),
        root=ROOT,
        platform_available=False,
    )
    assert unavailable.enabled is False
    assert unavailable.response("/").status == 404

    for section in ("http", "api", "platform", "webui"):
        configuration = enabled_config()
        configuration.data[section]["enabled"] = False
        disabled = WebUIService(configuration, root=ROOT)
        assert disabled.enabled is False
        assert disabled.response("/").status == 404
        assert disabled.response("/ui/app.js").status == 404


def test_webui_is_default_on_but_every_explicit_disable_is_authoritative():
    service = WebUIService(Configuration({}), root=ROOT, platform_available=True)

    assert service.enabled is True
    assert service.response("/").status == 200

    for section in ("http", "api", "platform", "webui"):
        disabled = WebUIService(
            Configuration({section: {"enabled": False}}),
            root=ROOT,
            platform_available=True,
        )
        assert disabled.enabled is False


def test_native_http_serves_get_and_head_with_strict_browser_headers(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(http_module, "config", enabled_config())
    database = Database(tmp_path / "state" / "notifinho.db")
    database.migrate()
    server = HTTPServer(
        ("127.0.0.1", 0),
        Dispatcher(),
        Router(),
        1_048_576,
        "",
        platform_database=database,
    )
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        page = http_request(server.server_port, "GET", "/")
        script = http_request(server.server_port, "GET", "/ui/app.js")
        head = http_request(server.server_port, "HEAD", "/ui/styles.css")
        missing = http_request(server.server_port, "GET", "/ui/missing.js")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)

    page_headers = dict(page[1])
    assert page[0] == 200
    assert page_headers["Content-Type"] == "text/html; charset=utf-8"
    assert page_headers["Cache-Control"] == "no-store"
    assert page_headers["X-Frame-Options"] == "DENY"
    assert page_headers["X-Content-Type-Options"] == "nosniff"
    assert page_headers["Referrer-Policy"] == "no-referrer"
    assert page_headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert "frame-ancestors 'none'" in page_headers["Content-Security-Policy"]
    assert script[0] == 200 and script[2]
    assert head[0] == 200 and head[2] == b""
    assert int(dict(head[1])["Content-Length"]) > 0
    assert missing[0] == 404 and missing[2] == b""
    assert set(SECURITY_HEADERS).issubset(set(page[1]))


def test_webui_markup_is_semantic_external_and_complete():
    markup = (ROOT / "src" / "webui" / "index.html").read_text(encoding="utf-8")
    inspector = MarkupInspector()
    inspector.feed(markup)

    required = {
        "bootstrap-form",
        "bootstrap-token",
        "login-form",
        "app-shell",
        "primary-nav",
        "main-content",
        "view-dashboard",
        "view-destinations",
        "view-routes",
        "view-tokens",
        "view-deliveries",
        "view-audit",
        "view-users",
        "view-settings",
        "view-data",
        "view-account",
        "configuration-status",
        "configuration-summary",
        "configuration-inputs",
        "preferences-form",
        "destination-dialog",
        "route-dialog",
        "token-dialog",
        "preview-dialog",
        "secret-dialog",
        "import-dialog",
    }
    assert required <= inspector.ids
    assert inspector.scripts == ["/ui/app.js"]
    assert inspector.stylesheets == ["/ui/styles.css"]
    assert inspector.inline_handlers == []
    assert "<style" not in markup
    assert "javascript:" not in markup.casefold()


def test_webui_uses_same_origin_api_without_unsafe_dom_or_secret_persistence():
    script = (ROOT / "src" / "webui" / "app.js").read_text(encoding="utf-8")

    for endpoint in (
        "/bootstrap",
        "/session",
        "/destinations",
        "/routes",
        "/tokens",
        "/deliveries",
        "/audit-events",
        "/users",
        "/preferences",
        "/portability/export",
        "/portability/preview",
        "/portability/import",
        "/migrations/v1/preview",
        "/migrations/v1/import",
        "/configuration/inventory",
        "/configuration/migration/preview",
        "/configuration/migration/apply",
        "/configuration/routing-authority",
        "/backups",
        "/account/password",
    ):
        assert endpoint in script
    assert 'const API = "/api/v2"' in script
    assert 'credentials: "same-origin"' in script
    assert 'cache: "no-store"' in script
    assert '["delivered", "success"].includes(item.outcome)' in script
    assert 'delivery.success ? `Test delivery sent successfully (${detail}).`' in script
    assert 'actionButton("Reset password", "reset-user", item.id)' in script
    assert 'if (!self)' in script
    assert 'headers["X-CSRF-Token"]' in script
    assert "navigator.clipboard.writeText" in script
    assert "textContent" in script
    for forbidden in (
        "innerHTML",
        "outerHTML",
        "insertAdjacentHTML",
        "document.write",
        "localStorage",
        "sessionStorage",
        "eval(",
        "new Function",
    ):
        assert forbidden not in script


def test_production_image_already_packages_webui_and_icon():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "COPY src /notifinho/src" in dockerfile
    assert "COPY assets /notifinho/assets" in dockerfile
    assert (ROOT / "src" / "webui" / "index.html").is_file()
    assert (ROOT / "src" / "webui" / "app.js").is_file()
    assert (ROOT / "src" / "webui" / "styles.css").is_file()
    assert (ROOT / "assets" / "icons" / "notifinho.png").is_file()
