"""Security and backend API foundation tests for v1.9."""

from __future__ import annotations

import json
import os

from pathlib import Path

import pytest
import yaml

from api.audit import AuditLog
from api.config_service import ConfigService
from api.schema import mask_secrets, validate_config
from api.security import (
    Principal,
    RateLimiter,
    TokenAuthenticator,
    hash_password,
    hash_token,
    verify_password,
)
from api.service import APIService
from dispatcher import Dispatcher


class Configuration:
    def __init__(self, data):
        self.data = data
        self.reload_count = 0

    def get(self, *keys, default=None):
        value = self.data
        for key in keys:
            if not isinstance(value, dict) or key not in value:
                return default
            value = value[key]
        return value

    def reload(self):
        self.reload_count += 1


class Router:
    def __init__(self):
        self.items = []

    def route(self, item):
        self.items.append(item)
        return True


def token_config(token_hash, sources=("home_lab",), role="application", limit=60):
    return {
        "api": {
            "enabled": True,
            "tokens": {
                "synthetic-client": {
                    "token_sha256": token_hash,
                    "role": role,
                    "sources": list(sources),
                    "rate_limit_per_minute": limit,
                }
            },
        }
    }


def test_token_authentication_is_hashed_scoped_and_timing_safe():
    secret = "synthetic-application-secret"
    auth = TokenAuthenticator(Configuration(token_config(hash_token(secret))))
    principal = auth.authenticate(secret, source="home_lab")

    assert principal is not None
    assert principal.name == "synthetic-client"
    assert principal.allows("home_lab") is True
    assert auth.authenticate(secret, source="another_source") is None
    assert auth.authenticate("wrong", source="home_lab") is None
    assert auth.authenticate(secret, require_admin=True) is None


def test_token_file_must_not_be_group_or_world_readable(tmp_path):
    path = tmp_path / "token"
    path.write_text("synthetic-file-secret", encoding="utf-8")
    config = token_config("")
    settings = config["api"]["tokens"]["synthetic-client"]
    settings.pop("token_sha256")
    settings["token_file"] = str(path)
    auth = TokenAuthenticator(Configuration(config))

    path.chmod(0o644)
    assert auth.authenticate("synthetic-file-secret", source="home_lab") is None
    path.chmod(0o600)
    assert auth.authenticate("synthetic-file-secret", source="home_lab") is not None

    link = tmp_path / "token-link"
    link.symlink_to(path)
    settings["token_file"] = str(link)
    assert auth.authenticate("synthetic-file-secret", source="home_lab") is None


def test_password_hash_foundation_uses_salt_and_rejects_short_passwords():
    first = hash_password("correct horse battery staple")
    second = hash_password("correct horse battery staple")
    assert first != second
    assert verify_password("correct horse battery staple", first) is True
    assert verify_password("wrong password", first) is False
    with pytest.raises(ValueError):
        hash_password("too-short")


def test_rate_limiter_is_scoped_by_principal_and_client():
    moments = iter((0.0, 1.0, 2.0, 61.0))
    limiter = RateLimiter(clock=lambda: next(moments))
    principal = Principal("client", "application", frozenset({"source"}), 2)
    assert limiter.allow(principal, "127.0.0.1") is True
    assert limiter.allow(principal, "127.0.0.1") is True
    assert limiter.allow(principal, "127.0.0.1") is False
    assert limiter.allow(principal, "127.0.0.1") is True


def test_masked_config_round_trip_preserves_secret_leaves(tmp_path):
    path = tmp_path / "config.yaml"
    original = {
        "http": {"enabled": True, "port": 8080, "shared_secret": "keep-me"},
        "outputs": {
            "discord": {
                "enabled": True,
                "default": {"webhook": "https://discord.invalid/api/webhooks/redacted"},
            }
        },
        "api": {
            "enabled": True,
            "tokens": {
                "client": {
                    "token_sha256": "a" * 64,
                    "role": "application",
                    "sources": ["home_lab"],
                }
            },
        },
    }
    path.write_text(yaml.safe_dump(original, sort_keys=False), encoding="utf-8")
    path.chmod(0o600)
    configuration = Configuration(original)
    service = ConfigService(path, configuration)
    masked = service.read_masked()

    assert isinstance(masked["api"]["tokens"], dict)
    assert masked["http"]["shared_secret"] == "<configured>"
    assert masked["outputs"]["discord"]["default"]["webhook"] == "<configured>"
    assert masked["api"]["tokens"]["client"]["token_sha256"] == "<configured>"

    masked["http"]["port"] = 8081
    backup = service.replace(masked)
    saved = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert saved["http"]["port"] == 8081
    assert saved["http"]["shared_secret"] == "keep-me"
    assert saved["api"]["tokens"]["client"]["token_sha256"] == "a" * 64
    assert backup.is_file()
    assert backup.stat().st_mode & 0o077 == 0
    assert path.stat().st_mode & 0o077 == 0
    assert configuration.reload_count == 1


def test_configuration_validation_rejects_plain_tokens_and_bad_routes():
    errors = validate_config({
        "api": {
            "tokens": {
                "bad": {
                    "token": "plaintext",
                    "role": "owner",
                    "sources": "",
                }
            }
        },
        "routing": {"source": {"outputs": []}},
    })
    rendered = "; ".join(errors)
    assert ".token is not allowed" in rendered
    assert "role must be admin or application" in rendered
    assert "outputs must be a non-empty list" in rendered


@pytest.mark.parametrize(
    "webhook",
    ["PASTE_HERE", "http://example.invalid/hook", "not-a-url", ""],
)
def test_configuration_validation_rejects_invalid_teams_webhooks(webhook):
    errors = validate_config({
        "outputs": {"teams": {"default": {"webhook": webhook}}},
        "routing": {
            "generic": {
                "outputs": [{"output": "teams", "target": "default"}],
            }
        },
    })
    rendered = "; ".join(errors)

    if webhook:
        assert "must be a valid HTTPS URL" in rendered
    else:
        assert "webhook is required" in rendered


def test_generic_event_api_enforces_source_scope_and_returns_delivery_state():
    secret = "synthetic-event-secret"
    config = Configuration(token_config(hash_token(secret)))
    router = Router()
    service = APIService(Dispatcher(), router, config)
    headers = {"Authorization": f"Bearer {secret}"}
    event = {
        "schema": "notifinho.event.v1",
        "source": "home_lab",
        "title": "Synthetic event",
        "message": "Synthetic scoped event delivery.",
        "severity": "warning",
        "status": "active",
    }

    status, response = service.handle("POST", "/api/events", event, headers, "127.0.0.1")
    assert status == 202
    assert response == {"accepted": True, "delivered": True}
    assert [item.source for item in router.items] == ["home_lab"]

    denied = dict(event, source="other")
    status, _ = service.handle("POST", "/api/events", denied, headers, "127.0.0.2")
    assert status == 401


def test_generic_event_preview_and_test_send_use_bounded_event_payload():
    secret = "synthetic-admin-secret"
    config = Configuration(
        token_config(
            hash_token(secret),
            sources=("*",),
            role="admin",
        )
    )
    router = Router()
    service = APIService(Dispatcher(), router, config)
    headers = {"Authorization": f"Bearer {secret}"}
    event = {
        "schema": "notifinho.event.v1",
        "source": "home_lab",
        "title": "Synthetic generic preview",
        "message": "Generic API preview presentation.",
        "severity": "information",
        "status": "active",
        "timestamp": "2026-07-16T16:46:00Z",
    }

    status, response = service.handle(
        "POST",
        "/api/preview",
        {"event": event, "output": "discord"},
        headers,
        "127.0.0.1",
    )
    rendered = json.dumps(response["preview"])

    assert status == 200
    assert "Synthetic generic preview" in rendered
    assert "Generic API preview presentation." in rendered
    assert "Xen Orchestra" not in rendered
    assert "Backup Successful" not in rendered
    assert "xologoname.png" not in rendered

    status, response = service.handle(
        "POST",
        "/api/test-send",
        {"event": event},
        headers,
        "127.0.0.2",
    )

    assert status == 200
    assert response == {"delivered": True}
    assert router.items[-1].source == "home_lab"


def test_health_is_public_only_when_api_is_enabled():
    enabled = APIService(Dispatcher(), Router(), Configuration({"api": {"enabled": True}}))
    disabled = APIService(Dispatcher(), Router(), Configuration({"api": {"enabled": False}}))
    assert enabled.handle("GET", "/api/health", None, {}, "127.0.0.1")[0] == 200
    assert disabled.handle("GET", "/api/health", None, {}, "127.0.0.1")[0] == 404


def test_audit_log_is_private_safe_and_owner_only(tmp_path):
    path = tmp_path / "audit.log"
    path.write_text("", encoding="utf-8")
    path.chmod(0o644)
    AuditLog(path).write("client", "/api/events?token=must-not-appear", "202", "source")
    content = path.read_text(encoding="utf-8")
    record = json.loads(content)
    assert record["principal"] == "client"
    assert record["path"] == "/api/events"
    assert "must-not-appear" not in content
    assert path.stat().st_mode & 0o077 == 0


def test_mask_secrets_does_not_mutate_input():
    value = {"nested": {"password": "secret", "enabled": True}}
    masked = mask_secrets(value)
    assert masked["nested"]["password"] == "<configured>"
    assert value["nested"]["password"] == "secret"
