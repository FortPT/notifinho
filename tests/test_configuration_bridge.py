"""Mounted YAML inventory, takeover, rollback, and routing-authority tests."""

from __future__ import annotations

import json

import pytest
import yaml

import router as router_module

from api.config_service import ConfigService
from api.security import hash_password
from models import Notification
from storage.audit_events import AuditEventStore
from storage.backups import StateBackupStore
from storage.configuration_bridge import ConfigurationBridgeService
from storage.database import Database
from storage.delivery import DeliveryResult, DeliverySummary
from storage.portability import PlatformPortabilityService
from storage.routing_bridge import PlatformRoutingBridge
from storage.users import UserStore


PASSWORD = "correct horse battery staple"
PRIVATE_WEBHOOK = "https://discord.com/api/webhooks/123/private-mounted-value"


class Configuration:
    def __init__(self, path):
        self.path = path
        self.reload()

    def reload(self):
        self.data = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}

    def get(self, *keys, default=None):
        value = self.data
        for key in keys:
            if not isinstance(value, dict) or key not in value:
                return default
            value = value[key]
        return value


def fast_hash(password: str) -> str:
    return hash_password(password, salt=b"\x0b" * 16, iterations=1_000)


def mounted_yaml(authority="yaml") -> str:
    return f"""
smtp:
  host: 0.0.0.0
  port: 8025
http:
  enabled: true
  port: 8080
  shared_secret: never-return-this
platform:
  enabled: true
  routing_authority: {authority}
outputs:
  discord:
    enabled: true
    alfa:
      webhook: {PRIVATE_WEBHOOK}
routing:
  dell_idrac:
    outputs:
      - output: discord
        target: alfa
        match:
          hosts: [ALFA]
"""


@pytest.fixture
def bridge_state(tmp_path):
    config_path = tmp_path / "config" / "config.yaml"
    config_path.parent.mkdir()
    config_path.write_text(mounted_yaml(), encoding="utf-8")
    configuration = Configuration(config_path)
    config_service = ConfigService(config_path, configuration)
    database = Database(tmp_path / "state" / "notifinho.db")
    database.migrate()
    users = UserStore(database, password_hasher=fast_hash)
    admin = users.bootstrap_admin("administrator", PASSWORD)
    audit = AuditEventStore(database)
    portability = PlatformPortabilityService(database, audit=audit)
    backups = StateBackupStore(database, audit=audit)
    bridge = ConfigurationBridgeService(
        config_service,
        portability,
        backups,
        audit=audit,
    )
    return {
        "path": config_path,
        "configuration": configuration,
        "config_service": config_service,
        "database": database,
        "admin": admin,
        "portability": portability,
        "backups": backups,
        "bridge": bridge,
    }


def test_inventory_detects_mounted_resources_without_returning_credentials(
    bridge_state,
):
    state = bridge_state
    inventory = state["bridge"].inventory(state["admin"].actor)
    encoded = json.dumps(inventory, sort_keys=True)
    plan, detected, _warnings = state["bridge"].preview(state["admin"].actor)

    assert inventory["authority"] == "yaml"
    assert inventory["migration_available"] is True
    assert inventory["summary"] == {
        "inputs": 2,
        "outputs": 1,
        "routes": 1,
        "migratable_outputs": 1,
        "migratable_routes": 1,
    }
    assert inventory["outputs"][0]["credential_configured"] is True
    assert inventory["routes"][0]["filters"] == {"hosts": ["ALFA"]}
    assert PRIVATE_WEBHOOK not in encoded
    assert "never-return-this" not in encoded
    assert plan.valid is True
    assert detected["fingerprint"] == plan.fingerprint
    assert PRIVATE_WEBHOOK not in json.dumps(plan.public(), sort_keys=True)


def test_confirmed_takeover_creates_backups_imports_secrets_and_switches_authority(
    bridge_state,
):
    state = bridge_state
    actor = state["admin"].actor
    plan, _inventory, _warnings = state["bridge"].preview(actor)
    result = state["bridge"].activate(actor, plan.fingerprint)
    live = yaml.safe_load(state["path"].read_text(encoding="utf-8"))

    assert result["destinations_created"] == 1
    assert result["routes_created"] == 1
    assert result["authority"] == "database"
    assert live["platform"]["routing_authority"] == "database"
    assert (state["path"].parent / "backups" / result["configuration_backup"]).is_file()
    assert state["backups"].list(actor)[0].id == result["state_backup"]
    with state["database"].connect() as connection:
        destination = connection.execute(
            "SELECT secret_id, enabled FROM destinations"
        ).fetchone()
        secret = connection.execute(
            "SELECT id FROM secret_records WHERE id = ?",
            (destination["secret_id"],),
        ).fetchone()
        route = connection.execute("SELECT enabled FROM routes").fetchone()
    assert secret is not None
    assert bool(destination["enabled"]) is True
    assert bool(route["enabled"]) is True
    assert PRIVATE_WEBHOOK.encode() not in state["database"].path.read_bytes()
    with pytest.raises(ValueError, match="already authoritative"):
        state["bridge"].activate(actor, plan.fingerprint)


def test_authority_rollback_retains_both_configurations_and_is_confirmed(
    bridge_state,
):
    state = bridge_state
    actor = state["admin"].actor
    plan, _inventory, _warnings = state["bridge"].preview(actor)
    state["bridge"].activate(actor, plan.fingerprint)

    with pytest.raises(ValueError, match="confirmation"):
        state["bridge"].set_authority(actor, "yaml", "wrong")
    fallback = state["bridge"].set_authority(
        actor,
        "yaml",
        "USE YAML ROUTING",
    )
    restored = state["bridge"].set_authority(
        actor,
        "database",
        "USE DATABASE ROUTING",
    )

    assert fallback["previous"] == "database"
    assert fallback["authority"] == "yaml"
    assert restored["authority"] == "database"
    assert state["bridge"].inventory(actor)["authority"] == "database"
    with state["database"].connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM routes").fetchone()[0] == 1


def test_failed_config_switch_removes_only_new_database_resources(
    bridge_state,
    monkeypatch,
):
    state = bridge_state
    actor = state["admin"].actor
    plan, _inventory, _warnings = state["bridge"].preview(actor)

    def fail(_candidate):
        raise OSError("synthetic config replacement failure")

    monkeypatch.setattr(state["config_service"], "replace", fail)
    with pytest.raises(OSError, match="synthetic"):
        state["bridge"].activate(actor, plan.fingerprint)
    with state["database"].connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM routes").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM destinations").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM secret_records").fetchone()[0] == 0
    assert state["bridge"].inventory(actor)["authority"] == "yaml"
    assert len(state["backups"].list(actor)) == 1


class RecordingAdapter:
    def __init__(self):
        self.events = []

    def __call__(self, destination, secret_value, notification):
        self.events.append((destination.name, secret_value, notification.source))
        return DeliveryResult(True, response_status=204)


class Registry:
    def __init__(self, adapter):
        self.adapter = adapter

    def delivery_adapters(self):
        return {"discord": self.adapter}


def test_platform_routing_bridge_delivers_legacy_event_after_takeover(
    bridge_state,
):
    state = bridge_state
    actor = state["admin"].actor
    plan, _inventory, _warnings = state["bridge"].preview(actor)
    state["bridge"].activate(actor, plan.fingerprint)
    adapter = RecordingAdapter()
    bridge = PlatformRoutingBridge(state["database"], registry=Registry(adapter))
    notification = Notification(
        source="dell_idrac",
        title="Synthetic hardware alert",
        metadata={"host": "ALFA", "severity": "warning"},
    )

    summary = bridge.route(notification)

    assert summary == DeliverySummary(1, 1, 0, 1)
    assert adapter.events == [
        ("Imported discord alfa", PRIVATE_WEBHOOK.encode(), "dell_idrac")
    ]


class StubPlatform:
    def __init__(self, summary):
        self.summary = summary
        self.notifications = []

    def route(self, notification):
        self.notifications.append(notification)
        return self.summary


def test_router_uses_exactly_one_authority(monkeypatch):
    configuration = type("RoutingConfiguration", (), {
        "get": staticmethod(lambda *keys, default=None: (
            "database" if keys == ("platform", "routing_authority") else default
        )),
    })()
    monkeypatch.setattr(router_module, "config", configuration)
    router = router_module.Router()
    router.platform = StubPlatform(DeliverySummary(1, 1, 0, 1))
    router.outputs = {"discord": pytest.fail}
    notification = Notification(source="generic")

    assert router.route(notification) is True
    assert router.platform.notifications == [notification]
