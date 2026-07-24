"""End-to-end HTTP transport tests for the v1.9 backend boundary."""

from __future__ import annotations

import http.client
import json
import threading

from pathlib import Path

import inputs.http as http_module

from api.audit import AuditLog
from api.security import hash_token
from dispatcher import Dispatcher
from inputs.http import HTTPServer


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
    def __init__(self):
        self.items = []

    def route(self, item):
        self.items.append(item)
        return True


class RunningServer:
    def __init__(self, monkeypatch, tmp_path, limit=60):
        secret = "synthetic-v190-api-secret"
        configuration = Configuration({
            "api": {
                "enabled": True,
                "tokens": {
                    "client": {
                        "token_sha256": hash_token(secret),
                        "role": "application",
                        "sources": ["home_assistant", "home_lab"],
                        "rate_limit_per_minute": limit,
                    }
                },
            }
        })
        monkeypatch.setattr(http_module, "config", configuration)
        self.secret = secret
        self.router = Router()
        self.server = HTTPServer(
            ("127.0.0.1", 0), Dispatcher(), self.router, 1_048_576, ""
        )
        self.server.api.audit = AuditLog(tmp_path / "audit.log")
        self.thread = threading.Thread(target=self.server.serve_forever)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


def request(port, method, path, payload=None, token=""):
    headers = {}
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    status = response.status
    raw = response.read()
    connection.close()
    return status, json.loads(raw) if raw else None


def event(source="home_lab"):
    return {
        "schema": "notifinho.event.v1",
        "source": source,
        "title": "Synthetic API event",
        "message": "End-to-end backend transport validation.",
        "severity": "information",
    }


def home_assistant_event():
    return {
        "schema": "notifinho.home_assistant.v1",
        "title": "Synthetic Home Assistant event",
        "message": "Source-scoped transport validation.",
        "severity": "information",
        "entity_id": "binary_sensor.synthetic_validation",
        "tags": ["synthetic"],
    }


def test_health_and_generic_event_transport(monkeypatch, tmp_path):
    with RunningServer(monkeypatch, tmp_path) as running:
        port = running.server.server_port
        health = request(port, "GET", "/api/health")
        missing = request(port, "POST", "/api/events", event())
        accepted = request(port, "POST", "/api/events", event(), running.secret)

    assert health[0] == 200
    assert health[1]["version"] == "2.4.0"
    assert missing[0] == 401
    assert accepted == (202, {"accepted": True, "delivered": True})
    assert [item.source for item in running.router.items] == ["home_lab"]


def test_source_endpoint_uses_api_scope_without_global_secret(monkeypatch, tmp_path):
    with RunningServer(monkeypatch, tmp_path) as running:
        port = running.server.server_port
        missing = request(port, "POST", "/home-assistant/events", home_assistant_event())
        accepted = request(
            port,
            "POST",
            "/home-assistant/events",
            home_assistant_event(),
            running.secret,
        )

    assert (missing[0], accepted[0]) == (401, 204)
    assert [item.source for item in running.router.items] == ["home_assistant"]


def test_api_rate_limit_returns_429(monkeypatch, tmp_path):
    with RunningServer(monkeypatch, tmp_path, limit=1) as running:
        port = running.server.server_port
        first = request(port, "POST", "/api/events", event(), running.secret)
        second = request(port, "POST", "/api/events", event(), running.secret)

    assert first[0] == 202
    assert second == (429, {"error": "rate limit exceeded"})
