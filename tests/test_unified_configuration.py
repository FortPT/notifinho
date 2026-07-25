"""v2.5 one-way database resource migration and isolation regressions."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest
import yaml

from api.config_service import ConfigService
from api.schema import mask_secrets
from api.security import hash_password
from storage.api_tokens import APITokenStore
from storage.configuration_sync import CONFIGURATION_MODEL, UnifiedConfigurationService
from storage.database import Database
from storage.destinations import DestinationStore
from storage.ownership import Actor
from storage.routes import RouteStore
from storage.secrets import SecretStore
from storage.settings import DEFAULT_INTEGRATION_SETTINGS
from storage.users import UserStore


PASSWORD = "correct horse battery staple"
TOKEN = "existing-hardware-token"
WEBHOOK = "https://discord.com/api/webhooks/123/private-value"


class Configuration:
    def __init__(self, path):
        self.path = path
        self.overlay = {}
        self.reload()

    def reload(self):
        self.disk = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        self.data = self._merged(self.disk, self.overlay)

    def apply_runtime_overlay(self, overlay):
        self.overlay = deepcopy(overlay)
        self.data = self._merged(self.disk, self.overlay)

    @classmethod
    def _merged(cls, base, overlay):
        result = deepcopy(base)
        for key, value in overlay.items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = cls._merged(result[key], value)
            else:
                result[key] = deepcopy(value)
        return result

    def get(self, *keys, default=None):
        value = self.data
        for key in keys:
            if not isinstance(value, dict) or key not in value:
                return default
            value = value[key]
        return deepcopy(value)


def fast_hash(password: str) -> str:
    return hash_password(password, salt=b"\x0c" * 16, iterations=1_000)


def source(state_dir, token_file) -> dict:
    return {
        "smtp": {"host": "0.0.0.0", "port": 8025},
        "http": {"enabled": True, "port": 8080, "shared_secret": "private-http"},
        "platform": {
            "enabled": True,
            "state_dir": str(state_dir),
            "configuration_model": "unified_yaml_v1",
            "backups": {
                "schedule": "daily",
                "time": "14:20",
                "weekday": 0,
                "day": 1,
                "target_id": "",
                "managed_mounts": True,
                "external_enabled": False,
                "external_type": "nfs",
                "external_path": "",
            },
        },
        "webui": {"enabled": True, "language": "en-GB"},
        "presentation": {"timezone": "Europe/Lisbon", "time_format": "24"},
        "api": {
            "enabled": True,
            "tokens": {
                "hardware": {
                    "enabled": True,
                    "role": "application",
                    "sources": ["redfish", "dell_idrac"],
                    "token_file": str(token_file),
                    "rate_limit_per_minute": 120,
                }
            },
        },
        "outputs": {
            "discord": {
                "enabled": True,
                "ops": {
                    "name": "Operations",
                    "enabled": True,
                    "shared": True,
                    "settings": {"channel_name": "#operations"},
                    "webhook": WEBHOOK,
                },
            }
        },
        "routing": {
            "dell_idrac": {
                "outputs": [
                    {
                        "name": "Critical iDRAC",
                        "input": "redfish",
                        "output": "discord",
                        "target": "ops",
                        "match": {"severities": ["critical"]},
                    }
                ]
            }
        },
        "notifications": {
            "xo": {"success": False, "skipped": True, "failure": True, "show_ids": False},
            "zabbix": {"show_ids": False},
            "dell_idrac": {"suppress_ipmi_session_audit_from": ["192.168.0.164"]},
            "unifi_protect": {"device_aliases": {"AA:BB:CC:DD:EE:FF": "CAM-01"}},
        },
        "home_assistant": {
            "aliases": {
                "endpoints": {"192.168.1.10": {"device": "HUB-01"}},
                "components": {
                    "homeassistant.components.ipp.coordinator": {
                        "device": "PRT-01",
                        "endpoint": "192.168.1.20",
                    }
                },
            }
        },
        "redfish": {"deduplication_window_seconds": 300},
    }


@pytest.fixture
def migrated(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    token_file = config_dir / "api-hardware-token.txt"
    token_file.write_text(TOKEN, encoding="utf-8")
    token_file.chmod(0o600)
    path = config_dir / "config.yaml"
    path.write_text(
        yaml.safe_dump(source(tmp_path / "state", token_file), sort_keys=False),
        encoding="utf-8",
    )
    path.chmod(0o640)
    configuration = Configuration(path)
    database = Database(tmp_path / "state" / "notifinho.db")
    assert database.migrate() == 8
    users = UserStore(database, password_hasher=fast_hash)
    admin = users.bootstrap_admin("administrator", PASSWORD)
    observer = users.create("observer", "observer secure password")
    service = UnifiedConfigurationService(ConfigService(path, configuration), database)
    return {
        "path": path,
        "configuration": configuration,
        "database": database,
        "admin": Actor(admin.id, "admin"),
        "observer": Actor(observer.id, "user"),
        "service": service,
    }


def test_first_sync_migrates_every_webui_resource_and_normalizes_yaml(migrated):
    status = migrated["service"].synchronize(force=True)
    saved = yaml.safe_load(migrated["path"].read_text(encoding="utf-8"))

    assert status.ready is True and status.changed is True
    assert status.errors == ()
    assert saved["platform"]["configuration_model"] == CONFIGURATION_MODEL
    assert migrated["path"].stat().st_mode & 0o777 == 0o640
    for section in (
        "outputs",
        "routing",
        "notifications",
        "presentation",
        "home_assistant",
        "redfish",
    ):
        assert section not in saved
    assert "tokens" not in saved["api"]
    assert "backups" not in saved["platform"]
    assert "language" not in saved["webui"]

    destinations = migrated["service"].list_destinations(migrated["observer"])
    routes = migrated["service"].list_routes(migrated["observer"])
    assert [item.name for item in destinations] == ["Operations"]
    assert [item.name for item in routes] == ["Critical iDRAC"]
    assert routes[0].input_type == "redfish"


def test_legacy_application_token_keeps_the_same_value(migrated):
    assert migrated["service"].synchronize().ready
    principal = APITokenStore(migrated["database"]).authenticate(TOKEN, "dell_idrac")
    assert principal is not None
    assert principal.token_name == "hardware"
    assert principal.allows("redfish")


def test_migrated_settings_are_available_in_webui_and_runtime_overlay(migrated):
    assert migrated["service"].synchronize().ready
    settings = migrated["service"].integration_settings()
    assert settings["errors"] == []
    assert settings["settings"]["dell_idrac"]["suppress_ipmi_session_audit_from"] == [
        "192.168.0.164"
    ]
    assert settings["settings"]["unifi_protect"]["device_aliases"] == {
        "AABBCCDDEEFF": "CAM-01"
    }
    assert migrated["service"].backup_settings()["schedule"] == "daily"
    assert migrated["service"].preferences() == {
        "timezone": "Europe/Lisbon",
        "language": "en-GB",
        "time_format": "24",
    }
    assert migrated["configuration"].get(
        "redfish", "deduplication_window_seconds"
    ) == 300
    assert migrated["configuration"].get(
        "home_assistant", "aliases", "endpoints", "192.168.1.10", "device"
    ) == "HUB-01"


def test_database_crud_does_not_rewrite_core_yaml(migrated):
    assert migrated["service"].synchronize().ready
    before = migrated["path"].read_bytes()
    secrets = SecretStore(migrated["database"])
    secret = secrets.create(
        migrated["admin"],
        migrated["admin"].user_id,
        "Automation webhook",
        "discord-credentials",
        {"url": "https://discord.com/api/webhooks/456/private"},
    )
    destinations = DestinationStore(migrated["database"])
    destination = destinations.create(
        migrated["admin"],
        migrated["admin"].user_id,
        "Automation",
        "discord",
        secret_id=secret.id,
        settings={"channel_name": "#automation"},
        shared=True,
    )
    route = RouteStore(migrated["database"]).create(
        migrated["admin"],
        migrated["admin"].user_id,
        "Automation HTTP",
        "home_assistant",
        destination.id,
        input_type="http",
    )
    assert route.destination_id == destination.id
    assert migrated["path"].read_bytes() == before


def test_invalid_database_managed_yaml_section_is_rejected_without_losing_resources(migrated):
    assert migrated["service"].synchronize().ready
    saved = yaml.safe_load(migrated["path"].read_text(encoding="utf-8"))
    saved["outputs"] = {"discord": {"enabled": True}}
    migrated["path"].write_text(yaml.safe_dump(saved, sort_keys=False), encoding="utf-8")

    status = migrated["service"].synchronize(force=True)
    assert status.ready is False
    assert "outputs is database-managed" in " ".join(status.errors)
    destinations, errors = DestinationStore(migrated["database"]).list_visible_safe(
        migrated["admin"]
    )
    assert [item.name for item in destinations] == ["Operations"]
    assert errors == []


def test_one_damaged_settings_row_uses_default_without_breaking_other_settings(migrated):
    assert migrated["service"].synchronize().ready
    with migrated["database"].transaction() as connection:
        connection.execute(
            """
            UPDATE settings_records SET value_json = ?
            WHERE namespace = 'integration' AND setting_key = 'zabbix'
            """,
            ("not-json",),
        )

    status = migrated["service"].synchronize(force=True)
    values = migrated["service"].integration_settings()
    assert status.ready is True
    assert any("integration.zabbix" in error for error in status.errors)
    assert values["settings"]["zabbix"] == DEFAULT_INTEGRATION_SETTINGS["zabbix"]
    assert values["settings"]["xo"]["show_ids"] is False
    assert values["errors"][0]["resource"] == "zabbix"


def test_one_damaged_destination_or_route_does_not_hide_valid_rows(migrated):
    assert migrated["service"].synchronize().ready
    destinations = DestinationStore(migrated["database"])
    routes = RouteStore(migrated["database"])
    original = destinations.list_visible(migrated["admin"])[0]
    with migrated["database"].transaction() as connection:
        connection.execute(
            "UPDATE destinations SET settings_json = 'not-json' WHERE id = ?",
            (original.id,),
        )
    valid_destination = destinations.create(
        migrated["admin"],
        migrated["admin"].user_id,
        "Valid destination",
        "discord",
        settings={},
        shared=True,
    )
    valid_route = routes.create(
        migrated["admin"],
        migrated["admin"].user_id,
        "Valid route",
        "zabbix",
        valid_destination.id,
        input_type="smtp",
    )
    with migrated["database"].transaction() as connection:
        connection.execute(
            "UPDATE routes SET filters_json = 'not-json' WHERE name = 'Critical iDRAC'"
        )

    destination_items, destination_errors = destinations.list_visible_safe(
        migrated["observer"]
    )
    route_items, route_errors = routes.list_visible_safe(migrated["observer"])
    assert [item.id for item in destination_items] == [valid_destination.id]
    assert destination_errors[0]["resource_id"] == original.id
    assert [item.id for item in route_items] == [valid_route.id]
    assert route_errors[0]["code"] == "route_record_invalid"


def test_migration_is_idempotent(migrated):
    first = migrated["service"].synchronize(force=True)
    config_after_first = migrated["path"].read_bytes()
    with migrated["database"].connect() as connection:
        counts_before = tuple(
            int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("destinations", "routes", "api_tokens", "settings_records")
        )
    second = migrated["service"].synchronize(force=True)
    with migrated["database"].connect() as connection:
        counts_after = tuple(
            int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("destinations", "routes", "api_tokens", "settings_records")
        )
    assert first.ready and second.ready
    assert migrated["path"].read_bytes() == config_after_first
    assert counts_after == counts_before


def test_nested_secrets_are_masked_without_hiding_token_metadata():
    masked = mask_secrets(
        {
            "api": {
                "tokens": {
                    "hardware": {
                        "enabled": True,
                        "token_file": "/run/secrets/hardware",
                        "token_sha256": "a" * 64,
                        "sources": ["redfish"],
                    }
                }
            },
            "outputs": {
                "webhook": {
                    "ops": {
                        "secret": {
                            "url": "https://example.invalid/private",
                            "headers": {"Authorization": "Bearer private"},
                        }
                    }
                }
            },
        }
    )
    assert masked["api"]["tokens"]["hardware"]["token_file"] == "<configured>"
    assert masked["api"]["tokens"]["hardware"]["sources"] == ["redfish"]
    assert masked["outputs"]["webhook"]["ops"]["secret"]["url"] == "<configured>"
