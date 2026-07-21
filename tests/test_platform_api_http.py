"""End-to-end native HTTP transport tests for the v2 platform API."""

from __future__ import annotations

import http.client
import json
import threading

import api.platform as platform_module
import inputs.http as http_module

from api.security import hash_password
from dispatcher import Dispatcher
from inputs.http import HTTPServer
from storage.database import Database
from storage.users import UserStore


PASSWORD = "correct horse battery staple"


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
        raise AssertionError("platform API must not use the YAML router")


def fast_hash(password):
    return hash_password(password, salt=b"\x09" * 16, iterations=1_000)


def request(port, method, path, payload=None, headers=None):
    sent_headers = dict(headers or {})
    body = None
    if payload is not None:
        sent_headers["Content-Type"] = "application/json"
        body = json.dumps(payload)
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    connection.request(method, path, body=body, headers=sent_headers)
    response = connection.getresponse()
    status = response.status
    response_headers = response.getheaders()
    raw = response.read()
    connection.close()
    return status, json.loads(raw) if raw else None, response_headers


def test_platform_session_crud_patch_and_delete_over_native_http(monkeypatch, tmp_path):
    database = Database(tmp_path / "state" / "notifinho.db")
    database.migrate()

    def users(database_value):
        return UserStore(database_value, password_hasher=fast_hash)

    monkeypatch.setattr(platform_module, "UserStore", users)
    users(database).bootstrap_admin("administrator", PASSWORD)
    configuration = Configuration({
        "api": {"enabled": True},
        "platform": {
            "enabled": True,
            "state_dir": str(tmp_path / "state"),
            "secure_cookies": False,
        },
    })
    monkeypatch.setattr(http_module, "config", configuration)
    server = HTTPServer(
        ("127.0.0.1", 0),
        Dispatcher(),
        Router(),
        1_048_576,
        "",
        database,
    )
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        login = request(
            server.server_port,
            "POST",
            "/api/v2/session",
            {"username": "administrator", "password": PASSWORD},
        )
        cookie_values = [value for name, value in login[2] if name == "Set-Cookie"]
        session_cookie = next(
            value.split(";", 1)[0]
            for value in cookie_values
            if "session=" in value
        )
        auth = {
            "Cookie": session_cookie,
            "X-CSRF-Token": login[1]["csrf_token"],
        }
        created = request(
            server.server_port,
            "POST",
            "/api/v2/destinations",
            {
                "name": "HTTP webhook",
                "output_type": "webhook",
                "settings": {"method": "POST"},
                "secret": {"url": "https://example.invalid/private"},
            },
            auth,
        )
        destination_id = created[1]["destination"]["id"]
        patched = request(
            server.server_port,
            "PATCH",
            f"/api/v2/destinations/{destination_id}",
            {"enabled": False},
            auth,
        )
        deleted = request(
            server.server_port,
            "DELETE",
            f"/api/v2/destinations/{destination_id}",
            headers=auth,
        )
        logout = request(
            server.server_port,
            "DELETE",
            "/api/v2/session",
            headers=auth,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)

    assert login[0] == 200
    assert len(cookie_values) == 2
    assert ("Cache-Control", "no-store") in login[2]
    assert ("X-Content-Type-Options", "nosniff") in login[2]
    assert ("Referrer-Policy", "no-referrer") in login[2]
    assert created[0] == 201
    assert "example.invalid" not in json.dumps(created[1])
    assert patched[0] == 200
    assert patched[1]["destination"]["enabled"] is False
    assert deleted[:2] == (204, None)
    assert logout[:2] == (204, None)
    assert len([value for name, value in logout[2] if name == "Set-Cookie"]) == 2
