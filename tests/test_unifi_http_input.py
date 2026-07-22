"""Native UniFi HTTP listener and lifecycle regression tests."""

from __future__ import annotations

import asyncio
import http.client
import json
import smtplib
import socket
import threading

from pathlib import Path

import pytest

import inputs.http as http_input_module
import inputs.smtp as smtp_input_module
import main as main_module

from dispatcher import Dispatcher
from inputs.http import HTTPInput, HTTPServer
from inputs.smtp import Handler as SMTPHandler
from inputs.smtp import SMTPInput


FIXTURES = Path(__file__).parent / "fixtures" / "unifi"


def fixture_payload(application: str) -> dict:
    filename = "client_disconnected.json" if application == "network" else "motion.json"
    return json.loads((FIXTURES / application / filename).read_text())


class RecordingRouter:
    def __init__(self):
        self.notifications = []

    def route(self, notification):
        self.notifications.append(notification)
        return True


class RunningServer:
    def __init__(
        self,
        dispatcher=None,
        router=None,
        max_body_bytes=1_048_576,
        shared_secret="",
    ):
        self.router = router or RecordingRouter()
        self.server = HTTPServer(
            ("127.0.0.1", 0),
            dispatcher or Dispatcher(),
            self.router,
            max_body_bytes,
            shared_secret,
        )
        self.thread = threading.Thread(target=self.server.serve_forever)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    @property
    def port(self):
        return self.server.server_port


def request(port, method, path, body=b"", headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    connection.request(method, path, body=body, headers=headers or {})
    response = connection.getresponse()
    status = response.status
    response.read()
    connection.close()
    return status


@pytest.mark.parametrize("application", ["network", "protect"])
def test_successful_unifi_post_dispatches_normalized_notification(application):
    body = json.dumps(fixture_payload(application)).encode()
    with RunningServer() as running:
        status = request(
            running.port,
            "POST",
            f"/unifi/{application}",
            body,
            {"Content-Type": "application/json"},
        )

    assert status == 204
    assert [item.source for item in running.router.notifications] == [
        f"unifi_{application}"
    ]


def test_application_vendor_json_content_type_is_accepted():
    body = json.dumps(fixture_payload("network")).encode()
    with RunningServer() as running:
        status = request(
            running.port,
            "POST",
            "/unifi/network",
            body,
            {"Content-Type": "application/vnd.synthetic+json"},
        )
    assert status == 204


def test_successful_http_info_logs_do_not_expose_private_payload_values(caplog):
    payload = fixture_payload("network")
    body = json.dumps(payload).encode()
    caplog.set_level("INFO", logger="notifinho.tests")
    with RunningServer() as running:
        assert request(
            running.port,
            "POST",
            "/unifi/network",
            body,
            {"Content-Type": "application/json"},
        ) == 204

    rendered = caplog.text
    assert "Detected UniFi Network webhook" in rendered
    for private_value in (
        payload["alarm_id"],
        payload["parameters"]["UNIFIclientIp"],
        payload["parameters"]["UNIFIclientMac"],
        payload["parameters"]["UNIFIhost"],
        payload["parameters"]["UNIFIlastConnectedToDeviceName"],
    ):
        assert private_value not in rendered


@pytest.mark.parametrize(
    ("path", "body", "content_type", "expected"),
    [
        ("/unifi/network", b"{broken", "application/json", 400),
        ("/unifi/network", b"{}", "text/plain", 400),
        ("/unknown", b"{}", "application/json", 404),
    ],
)
def test_invalid_http_requests(path, body, content_type, expected):
    with RunningServer() as running:
        status = request(
            running.port,
            "POST",
            path,
            body,
            {"Content-Type": content_type},
        )
    assert status == expected


def test_unsupported_method_returns_405_and_allow_header():
    with RunningServer() as running:
        status = request(running.port, "GET", "/unifi/network")
    assert status == 405


def test_body_limit_returns_413_before_parsing():
    with RunningServer(max_body_bytes=16) as running:
        status = request(
            running.port,
            "POST",
            "/unifi/network",
            b"x" * 17,
            {"Content-Type": "application/json"},
        )
    assert status == 413
    assert running.router.notifications == []


def test_shared_secret_success_and_failure_do_not_reveal_request_validity():
    body = json.dumps(fixture_payload("network")).encode()
    with RunningServer(shared_secret="synthetic-shared-secret") as running:
        missing = request(
            running.port,
            "POST",
            "/unifi/network",
            body,
            {"Content-Type": "application/json"},
        )
        wrong_on_unknown_path = request(
            running.port,
            "POST",
            "/unknown",
            b"not-json",
            {"X-Notifinho-Token": "wrong"},
        )
        success = request(
            running.port,
            "POST",
            "/unifi/network",
            body,
            {
                "Content-Type": "application/json",
                "X-Notifinho-Token": "synthetic-shared-secret",
            },
        )
    assert (missing, wrong_on_unknown_path, success) == (401, 401, 204)


def test_shared_secret_uses_timing_safe_comparison(monkeypatch):
    calls = []

    def compare(first, second):
        calls.append((first, second))
        return first == second

    monkeypatch.setattr(http_input_module.hmac, "compare_digest", compare)
    with RunningServer(shared_secret="synthetic-shared-secret") as running:
        status = request(
            running.port,
            "GET",
            "/unifi/network",
            headers={"X-Notifinho-Token": "synthetic-shared-secret"},
        )
    assert status == 405
    assert calls == [(b"synthetic-shared-secret", b"synthetic-shared-secret")]


def test_dispatcher_failure_is_isolated_from_later_requests():
    class DispatcherStub:
        def __init__(self):
            self.calls = 0

        def parse_webhook(self, application, payload):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("synthetic parser failure")
            return type("Notification", (), {"source": "unifi_network"})()

    dispatcher = DispatcherStub()
    body = json.dumps(fixture_payload("network")).encode()
    headers = {"Content-Type": "application/json"}
    with RunningServer(dispatcher=dispatcher) as running:
        first = request(running.port, "POST", "/unifi/network", body, headers)
        second = request(running.port, "POST", "/unifi/network", body, headers)

    assert (first, second) == (500, 204)
    assert dispatcher.calls == 2
    assert len(running.router.notifications) == 1


def test_http_input_disabled_does_not_bind(monkeypatch):
    class Config:
        def get(self, *keys, default=None):
            return False if keys == ("http", "enabled") else default

    monkeypatch.setattr(http_input_module, "config", Config())
    item = HTTPInput(Dispatcher(), RecordingRouter())
    assert item.start() is False
    assert item.server is None
    item.stop()


def test_http_input_graceful_startup_and_shutdown(monkeypatch):
    values = {
        ("http", "enabled"): True,
        ("http", "host"): "127.0.0.1",
        ("http", "port"): 0,
        ("http", "max_body_bytes"): 1024,
        ("http", "shared_secret"): "",
    }

    class Config:
        def get(self, *keys, default=None):
            return values.get(keys, default)

    monkeypatch.setattr(http_input_module, "config", Config())
    item = HTTPInput(Dispatcher(), RecordingRouter())
    assert item.start() is True
    assert item.thread is not None and item.thread.is_alive()
    item.stop()
    assert item.server is None
    assert item.thread is None


def test_existing_smtp_handler_still_dispatches_email(monkeypatch, tmp_path):
    class DispatcherStub:
        def parse(self, message):
            return type("Notification", (), {"source": "generic"})()

    router = RecordingRouter()
    handler = SMTPHandler(DispatcherStub(), router)
    monkeypatch.setattr(smtp_input_module, "Path", lambda _value: tmp_path)
    envelope = type(
        "Envelope",
        (),
        {
            "mail_from": "sender@example.invalid",
            "rcpt_tos": ["receiver@example.invalid"],
            "original_content": (
                b"From: sender@example.invalid\r\n"
                b"To: receiver@example.invalid\r\n"
                b"Subject: Synthetic\r\n\r\nBody"
            ),
        },
    )()

    result = asyncio.run(handler.handle_DATA(None, None, envelope))

    assert result == "250 Message accepted"
    assert len(router.notifications) == 1
    assert list(tmp_path.glob("*.eml"))


def test_application_lifecycle_starts_and_stops_smtp_and_http(monkeypatch):
    events = []

    class Component:
        def __init__(self, dispatcher=None, router=None):
            self.name = self.__class__.__name__

        def start(self):
            events.append((self.name, "start"))

        def stop(self):
            events.append((self.name, "stop"))

    class SMTP(Component):
        pass

    class HTTP(Component):
        pass

    monkeypatch.setattr(main_module, "Dispatcher", lambda: object())
    monkeypatch.setattr(main_module, "Router", lambda: object())
    monkeypatch.setattr(main_module, "SMTPInput", SMTP)
    monkeypatch.setattr(main_module, "HTTPInput", HTTP)
    monkeypatch.setattr(main_module, "initialize_state", lambda _config: None)
    monkeypatch.setattr(
        main_module.time,
        "sleep",
        lambda _seconds: (_ for _ in ()).throw(KeyboardInterrupt()),
    )

    assert main_module.main() == 0
    assert events == [
        ("SMTP", "start"),
        ("HTTP", "start"),
        ("HTTP", "stop"),
        ("SMTP", "stop"),
    ]


def _free_port() -> int:
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        return candidate.getsockname()[1]


@pytest.mark.parametrize("http_enabled", [False, True])
def test_real_smtp_and_optional_http_inputs_run_together(
    monkeypatch, tmp_path, http_enabled
):
    smtp_port = _free_port()
    values = {
        ("smtp", "host"): "127.0.0.1",
        ("smtp", "port"): smtp_port,
        ("http", "enabled"): http_enabled,
        ("http", "host"): "127.0.0.1",
        ("http", "port"): 0,
        ("http", "max_body_bytes"): 1_048_576,
        ("http", "shared_secret"): "",
    }

    class Config:
        def get(self, *keys, default=None):
            return values.get(keys, default)

    config = Config()
    monkeypatch.setattr(smtp_input_module, "config", config)
    monkeypatch.setattr(http_input_module, "config", config)
    monkeypatch.setattr(smtp_input_module, "Path", lambda _value: tmp_path)
    router = RecordingRouter()
    dispatcher = Dispatcher()
    smtp = SMTPInput(dispatcher, router)
    http = HTTPInput(dispatcher, router)
    try:
        smtp.start()
        assert http.start() is http_enabled
        with smtplib.SMTP("127.0.0.1", smtp_port, timeout=3) as client:
            client.sendmail(
                "sender@example.invalid",
                ["receiver@example.invalid"],
                (
                    "From: sender@example.invalid\r\n"
                    "To: receiver@example.invalid\r\n"
                    "Subject: Synthetic SMTP regression\r\n\r\n"
                    "Ordinary synthetic content"
                ),
            )
        if http_enabled:
            body = json.dumps(fixture_payload("network")).encode()
            assert request(
                http.server.server_port,
                "POST",
                "/unifi/network",
                body,
                {"Content-Type": "application/json"},
            ) == 204
    finally:
        http.stop()
        smtp.stop()

    expected = ["generic", "unifi_network"] if http_enabled else ["generic"]
    assert [item.source for item in router.notifications] == expected
