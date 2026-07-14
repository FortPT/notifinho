"""Native production HTTP input for UniFi Network, Protect, and Drive webhooks."""

from __future__ import annotations

import hmac
import json
import threading

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from config import config
from logger import log


ENDPOINTS = {
    "/unifi/network": "network",
    "/unifi/protect": "protect",
    "/unifi/drive": "drive",
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
    ):
        super().__init__(address, HTTPHandler)
        self.dispatcher = dispatcher
        self.router = router
        self.max_body_bytes = max_body_bytes
        self.shared_secret = shared_secret


class HTTPHandler(BaseHTTPRequestHandler):
    """Handle one request without retaining or logging its raw payload."""

    server: HTTPServer

    def do_POST(self) -> None:  # noqa: N802 - standard-library callback name
        if not self._authenticated():
            self._respond(401)
            return

        application = ENDPOINTS.get(self.path)
        if application is None:
            self._respond(404)
            return

        if not is_json_content_type(self.headers.get("Content-Type", "")):
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
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            self._respond(400)
            return

        try:
            notification = self.server.dispatcher.parse_webhook(
                application,
                payload,
            )
            if notification is None:
                self._respond(400)
                return
            self.server.router.route(notification)
        except Exception:
            log.exception("UniFi webhook processing failed")
            self._respond(500)
            return

        self._respond(204)

    def do_GET(self) -> None:  # noqa: N802
        self._unsupported_method()

    def do_PUT(self) -> None:  # noqa: N802
        self._unsupported_method()

    def do_PATCH(self) -> None:  # noqa: N802
        self._unsupported_method()

    def do_DELETE(self) -> None:  # noqa: N802
        self._unsupported_method()

    def do_HEAD(self) -> None:  # noqa: N802
        self._unsupported_method()

    def _unsupported_method(self) -> None:
        if not self._authenticated():
            self._respond(401)
            return
        self._respond(405, {"Allow": "POST"})

    def _authenticated(self) -> bool:
        expected = self.server.shared_secret
        if not expected:
            return True
        supplied = self.headers.get("X-Notifinho-Token", "")
        return hmac.compare_digest(
            str(supplied).encode("utf-8"),
            str(expected).encode("utf-8"),
        )

    def _respond(self, status: int, headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args) -> None:
        # Access logging can expose query strings or unexpected identifiers.
        return


class HTTPInput:
    """Configurable HTTP listener that shares the application lifecycle."""

    def __init__(self, dispatcher, router):
        self.dispatcher = dispatcher
        self.router = router
        self.enabled = bool(config.get("http", "enabled", default=False))
        self.host = str(config.get("http", "host", default="0.0.0.0"))
        self.port = int(config.get("http", "port", default=8080))
        configured_limit = int(
            config.get("http", "max_body_bytes", default=1_048_576)
        )
        self.max_body_bytes = max(1, configured_limit)
        self.shared_secret = str(
            config.get("http", "shared_secret", default="") or ""
        )
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
