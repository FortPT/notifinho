"""Native production HTTP input for supported JSON webhooks."""

from __future__ import annotations

import hmac
import json
import threading
import time

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from config import config
from api.service import APIService
from logger import log
from webui.service import SECURITY_HEADERS, WebUIService


ENDPOINTS = {
    "/unifi/network": "network",
    "/unifi/protect": "protect",
    "/unifi/drive": "drive",
    "/portainer/alerts": "portainer",
    "/proxmox/events": "proxmox",
    "/synology/events": "synology",
    "/redfish/events": "redfish",
    "/redfish/supermicro": "supermicro",
    "/redfish/hpe": "hpe",
    "/redfish/dell": "dell",
    "/home-assistant/events": "home_assistant",
}

SCOPED_SOURCES = {
    "redfish": "redfish",
    "supermicro": "supermicro",
    "hpe": "hpe_ilo",
    "dell": "dell_idrac",
    "home_assistant": "home_assistant",
}


def is_json_content_type(value: str) -> bool:
    media_type = str(value or "").split(";", 1)[0].strip().casefold()
    return media_type == "application/json" or (
        media_type.startswith("application/") and media_type.endswith("+json")
    )


class HTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        address,
        dispatcher,
        router,
        max_body_bytes: int,
        shared_secret: str,
        platform_database=None,
    ):
        super().__init__(address, HTTPHandler)
        self.dispatcher = dispatcher
        self.router = router
        self.max_body_bytes = max_body_bytes
        self.shared_secret = shared_secret
        self.api = APIService(
            dispatcher,
            router,
            config,
            platform_database=platform_database,
        )
        self.webui = WebUIService(
            config,
            platform_available=platform_database is not None,
        )
        self._seen: dict[str, float] = {}
        self._seen_lock = threading.Lock()

    def duplicate(self, notification) -> bool:
        key = str((notification.metadata or {}).get("deduplication_key") or "")
        if not key:
            return False
        window = max(
            1,
            int(config.get("redfish", "deduplication_window_seconds", default=300)),
        )
        now = time.monotonic()
        with self._seen_lock:
            self._seen = {
                item: observed
                for item, observed in self._seen.items()
                if now - observed < window
            }
            if key in self._seen:
                return True
            self._seen[key] = now
        return False


class HTTPHandler(BaseHTTPRequestHandler):
    """Handle one request without retaining or logging its raw payload."""

    server: HTTPServer

    def do_POST(self) -> None:  # noqa: N802 - standard-library callback name
        request_url = urlsplit(self.path)

        if request_url.path.startswith("/api/"):
            self._api_request("POST", request_url.path)
            return

        application = ENDPOINTS.get(request_url.path)
        if application is None:
            if not self._authenticated(request_url.path, request_url.query):
                self._respond(401)
                return
            self._respond(404)
            return

        if not self._authenticated_application(
            application,
            request_url.path,
            request_url.query,
        ):
            self._respond(401)
            return

        content_type = self.headers.get("Content-Type", "")
        form_encoded = (
            application == "synology"
            and str(content_type).split(";", 1)[0].strip().casefold()
            == "application/x-www-form-urlencoded"
        )
        if not is_json_content_type(content_type) and not form_encoded:
            self._respond(400)
            return

        try:
            length = int(self.headers.get("Content-Length", ""))
        except (TypeError, ValueError):
            self._respond(400)
            return
        if length < 0:
            self._respond(400)
            return
        if length > self.server.max_body_bytes:
            self._respond(413)
            return

        body = self.rfile.read(length)
        if len(body) > self.server.max_body_bytes:
            self._respond(413)
            return
        try:
            if form_encoded:
                values = parse_qs(
                    body.decode("utf-8"),
                    keep_blank_values=True,
                    strict_parsing=True,
                    max_num_fields=64,
                )
                if not values or any(len(items) != 1 for items in values.values()):
                    raise ValueError("invalid form fields")
                payload = {key: items[0] for key, items in values.items()}
            else:
                payload = json.loads(body.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError, ValueError):
            self._respond(400)
            return

        try:
            parsed = self.server.dispatcher.parse_webhook(
                application,
                payload,
            )
            if parsed is None:
                self._respond(400)
                return
            notifications = parsed if isinstance(parsed, list) else [parsed]
            if not notifications:
                self._respond(400)
                return
            for notification in notifications:
                if application in {"redfish", "supermicro", "hpe", "dell"} and self.server.duplicate(notification):
                    log.info("Duplicate Redfish event ignored")
                    continue
                self.server.router.route(notification)
        except Exception:
            log.exception("Webhook processing failed")
            self._respond(500)
            return

        self._respond(204)

    def do_GET(self) -> None:  # noqa: N802
        request_url = urlsplit(self.path)
        if request_url.path.startswith("/api/"):
            self._api_request("GET", request_url.path)
            return
        if self._webui_request(request_url.path):
            return
        self._unsupported_method()

    def do_PUT(self) -> None:  # noqa: N802
        request_url = urlsplit(self.path)
        if request_url.path.startswith("/api/"):
            self._api_request("PUT", request_url.path)
            return
        self._unsupported_method()

    def do_PATCH(self) -> None:  # noqa: N802
        request_url = urlsplit(self.path)
        if request_url.path.startswith("/api/"):
            self._api_request("PATCH", request_url.path)
            return
        self._unsupported_method()

    def do_DELETE(self) -> None:  # noqa: N802
        request_url = urlsplit(self.path)
        if request_url.path.startswith("/api/"):
            self._api_request("DELETE", request_url.path)
            return
        self._unsupported_method()

    def do_HEAD(self) -> None:  # noqa: N802
        request_url = urlsplit(self.path)
        if self._webui_request(request_url.path, head=True):
            return
        self._unsupported_method()

    def _webui_request(self, path: str, *, head: bool = False) -> bool:
        response = self.server.webui.response(path)
        if response is None:
            return False
        body = response.body
        self.send_response(response.status)
        if response.content_type:
            self.send_header("Content-Type", response.content_type)
        self.send_header("Cache-Control", response.cache_control)
        for name, value in SECURITY_HEADERS:
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body and not head:
            self.wfile.write(body)
        return True

    def _unsupported_method(self) -> None:
        request_url = urlsplit(self.path)
        if not self._authenticated(request_url.path, request_url.query):
            self._respond(401)
            return
        self._respond(405, {"Allow": "POST"})

    def _authenticated(self, path: str, query: str) -> bool:
        expected = self.server.shared_secret
        if not expected:
            return True
        supplied = self.headers.get("X-Notifinho-Token", "")
        if path in {"/portainer/alerts", "/synology/events"} and not supplied:
            values = parse_qs(query, keep_blank_values=True).get("token", [])
            supplied = values[0] if len(values) == 1 else ""
        return hmac.compare_digest(
            str(supplied).encode("utf-8"),
            str(expected).encode("utf-8"),
        )

    def _authenticated_application(self, application: str, path: str, query: str) -> bool:
        scoped_source = SCOPED_SOURCES.get(application)
        if not scoped_source:
            return self._authenticated(path, query)
        if self.server.shared_secret and self._authenticated(path, query):
            return True
        principal = self.server.api.authorize_source(
            self.headers,
            scoped_source,
            self.client_address[0],
        )
        return bool(principal)

    def _api_request(self, method: str, path: str) -> None:
        payload = None
        if method in {"POST", "PUT", "PATCH"}:
            content_type = self.headers.get("Content-Type", "")
            if not is_json_content_type(content_type):
                self._respond_json(400, {"error": "application/json required"})
                return
            try:
                length = int(self.headers.get("Content-Length", ""))
            except (TypeError, ValueError):
                self._respond_json(400, {"error": "invalid content length"})
                return
            if length < 0 or length > self.server.max_body_bytes:
                self._respond_json(413 if length > self.server.max_body_bytes else 400, None)
                return
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError):
                self._respond_json(400, {"error": "invalid JSON"})
                return
        response = self.server.api.handle_http(
            method,
            path,
            payload,
            self.headers,
            self.client_address[0],
        )
        self._respond_json(
            response.status,
            response.payload,
            response.headers,
        )

    def _respond(self, status: int, headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _respond_json(
        self,
        status: int,
        payload,
        headers: tuple[tuple[str, str], ...] = (),
    ) -> None:
        body = b""
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        if body:
            self.send_header("Content-Type", "application/json; charset=utf-8")
        platform_response = urlsplit(self.path).path.startswith("/api/v2/")
        if platform_response:
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            if not any(
                str(name).casefold() == "cache-control" for name, _value in headers
            ):
                self.send_header("Cache-Control", "no-store")
        if status == 405 and not any(
            str(name).casefold() == "allow" for name, _value in headers
        ):
            self.send_header("Allow", "GET, POST, PUT")
        for name, value in headers:
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        # Access logging can expose query strings or unexpected identifiers.
        return


class HTTPInput:
    """Configurable HTTP listener that shares the application lifecycle."""

    def __init__(self, dispatcher, router, *, platform_database=None):
        self.dispatcher = dispatcher
        self.router = router
        self.enabled = bool(config.get("http", "enabled", default=True))
        self.host = str(config.get("http", "host", default="0.0.0.0"))
        self.port = int(config.get("http", "port", default=8080))
        configured_limit = int(
            config.get("http", "max_body_bytes", default=1_048_576)
        )
        self.max_body_bytes = max(1, configured_limit)
        self.shared_secret = str(
            config.get("http", "shared_secret", default="") or ""
        )
        self.platform_database = platform_database
        self.server: HTTPServer | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> bool:
        if not self.enabled:
            log.info("HTTP input disabled")
            return False
        if self.server is not None:
            return True
        self.server = HTTPServer(
            (self.host, self.port),
            self.dispatcher,
            self.router,
            self.max_body_bytes,
            self.shared_secret,
            self.platform_database,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            name="notifinho-http",
            daemon=True,
        )
        self.thread.start()
        log.info("HTTP webhook input listening on %s:%s", self.host, self.server.server_port)
        return True

    def stop(self) -> None:
        if self.server is None:
            return
        log.info("Stopping HTTP webhook input...")
        self.server.shutdown()
        self.server.server_close()
        if self.thread is not None:
            self.thread.join(timeout=5)
        self.server = None
        self.thread = None
        log.info("HTTP webhook input stopped")
