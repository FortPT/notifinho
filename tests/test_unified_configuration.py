"""Single-source config.yaml synchronization and presentation regressions."""

from __future__ import annotations

import json

import pytest
import yaml

from api.config_service import ConfigService
from api.schema import mask_secrets
from api.security import hash_password
from storage.configuration_sync import CONFIGURATION_MODEL, UnifiedConfigurationService
from storage.database import Database
from storage.destinations import DestinationStore
from storage.ownership import Actor
from storage.routes import RouteStore
from storage.secrets import SecretStore
from storage.users import UserStore


PASSWORD = "correct horse battery staple"
WEBHOOK = "https://discord.com/api/webhooks/123/private-value"


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
    return hash_password(password, salt=b"\x0c" * 16, iterations=1_000)


def source(state_dir) -> dict:
    return {
        "http": {"enabled": True, "port": 8080, "shared_secret": "private-http"},
        "platform": {
            "enabled": True,
            "state_dir": str(state_dir),
            "routing_authority": "database",
        },
        "webui": {"enabled": True},
        "presentation": {"timezone": "Europe/Lisbon"},
        "api": {
            "enabled": True,
            "tokens": {
                "idrac": {
                    "token_sha256": "a" * 64,
                    "sources": ["dell_idrac"],
                    "rate_limit_per_minute": 30,
                }
            },
        },
        "outputs": {
            "discord": {
                "enabled": True,
                "ops": {
                    "name": "Operations",
                    "webhook": WEBHOOK,
                },
            }
        },
        "routing": {
            "dell_idrac": {
                "outputs": [
                    {
                        "output": "discord",
                        "target": "ops",
                        "match": {"severities": ["critical"]},
                    }
                ]
            }
        },
    }


@pytest.fixture
def unified(tmp_path):
    path = tmp_path / "config" / "config.yaml"
    path.parent.mkdir()
    path.write_text(yaml.safe_dump(source(tmp_path / "state"), sort_keys=False), encoding="utf-8")
    configuration = Configuration(path)
    config_service = ConfigService(path, configuration)
    database = Database(tmp_path / "state" / "notifinho.db")
    database.migrate()
    users = UserStore(database, password_hasher=fast_hash)
    admin = users.bootstrap_admin("administrator", PASSWORD)
    user = users.create("observer", "observer secure password")
    service = UnifiedConfigurationService(config_service, database)
    return {
        "path": path,
        "configuration": configuration,
        "config_service": config_service,
        "database": database,
        "admin": Actor(admin.id, "admin"),
        "user": Actor(user.id, "user"),
        "service": service,
    }


def test_first_sync_replaces_v202_authority_without_duplicate_fallbacks(unified):
    status = unified["service"].synchronize()
    saved = yaml.safe_load(unified["path"].read_text(encoding="utf-8"))

    assert status.ready is True and status.changed is True
    assert saved["platform"]["configuration_model"] == CONFIGURATION_MODEL
    assert "routing_authority" not in saved["platform"]
    assert len(unified["service"].list_destinations(unified["user"])) == 1
    assert len(unified["service"].list_routes(unified["user"])) == 1
    with unified["database"].connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM destinations").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM routes").fetchone()[0] == 1


def test_first_sync_matches_v202_imported_rows_instead_of_duplicating(unified):
    secret = SecretStore(unified["database"]).create(
        unified["admin"],
        unified["admin"].user_id,
        "Imported discord ops credential",
        "discord-webhook",
        WEBHOOK,
    )
    destination = DestinationStore(unified["database"]).create(
        unified["admin"],
        unified["admin"].user_id,
        "Imported discord ops",
        "discord",
        secret_id=secret.id,
        settings={"components_v2": True},
        shared=True,
    )
    route = RouteStore(unified["database"]).create(
        unified["admin"],
        unified["admin"].user_id,
        "Imported dell_idrac to discord ops 1",
        "dell_idrac",
        destination.id,
        filters={"severities": ["critical"]},
    )

    unified["service"].synchronize()
    destinations = unified["service"].list_destinations(unified["user"])
    routes = unified["service"].list_routes(unified["user"])
    assert [item.id for item in destinations] == [destination.id]
    assert [item.id for item in routes] == [route.id]


def test_external_yaml_edits_are_reflected_and_invalid_yaml_is_reported(unified):
    unified["service"].synchronize()
    saved = yaml.safe_load(unified["path"].read_text(encoding="utf-8"))
    saved["outputs"]["discord"]["secondary"] = {
        "name": "Secondary",
        "webhook": "https://discord.com/api/webhooks/456/other-private",
    }
    unified["path"].write_text(yaml.safe_dump(saved, sort_keys=False), encoding="utf-8")

    status = unified["service"].synchronize()
    assert status.ready is True
    assert {item.name for item in unified["service"].list_destinations(unified["user"])} == {
        "Operations",
        "Secondary",
    }

    unified["path"].write_text("outputs: [broken", encoding="utf-8")
    broken = unified["service"].synchronize(force=True)
    assert broken.ready is False
    assert "invalid" in " ".join(broken.errors).casefold()
    assert unified["configuration"].get("outputs", "discord", "secondary", "name") == "Secondary"
    assert len(unified["service"].list_destinations(unified["user"])) == 2
    assert unified["service"].preferences()["timezone"] == "Europe/Lisbon"


def test_admin_crud_writes_yaml_and_observer_cannot_mutate(unified):
    unified["service"].synchronize()
    created = unified["service"].create_destination(
        unified["admin"],
        {
            "name": "Automation webhook",
            "output_type": "webhook",
            "settings": {"method": "POST"},
            "secret": {"url": "https://example.invalid/events"},
            "enabled": True,
        },
    )
    saved = yaml.safe_load(unified["path"].read_text(encoding="utf-8"))
    assert saved["outputs"]["webhook"]["automation_webhook"]["secret"]["url"].endswith("/events")

    route = unified["service"].create_route(
        unified["admin"],
        {
            "name": "Automation route",
            "source": "home_lab",
            "destination_id": created.id,
            "filters": {"severities": ["warning"]},
            "priority": 25,
            "enabled": True,
        },
    )
    saved = yaml.safe_load(unified["path"].read_text(encoding="utf-8"))
    assert saved["routing"]["home_lab"]["outputs"][0]["id"]
    renamed = unified["service"].update_destination(
        unified["admin"], created.id, {"name": "Automation primary"}
    )
    assert renamed.name == "Automation primary"
    assert unified["service"].update_route(
        unified["admin"], route.id, {"enabled": False}
    ).enabled is False
    with pytest.raises(PermissionError):
        unified["service"].update_destination(
            unified["user"], created.id, {"enabled": False}
        )


def test_yaml_applications_and_preferences_are_safe_and_file_backed(unified):
    unified["service"].synchronize()
    applications = unified["service"].legacy_applications()
    assert applications == [
        {
            "id": applications[0]["id"],
            "name": "idrac",
            "role": "application",
            "source_scopes": ["dell_idrac"],
            "rate_limit_per_minute": 30,
            "version": 1,
            "created_at": None,
            "updated_at": None,
            "expires_at": None,
            "last_used_at": None,
            "revoked_at": None,
            "enabled": True,
            "management": "yaml",
            "credential_source": "SHA-256",
            "credential_available": True,
        }
    ]
    assert WEBHOOK not in json.dumps(applications)

    preferences = unified["service"].update_preferences(
        unified["admin"],
        {"timezone": "Atlantic/Azores", "language": "pt-PT", "time_format": "12"},
    )
    assert preferences == {
        "timezone": "Atlantic/Azores",
        "language": "pt-PT",
        "time_format": "12",
    }
    saved = yaml.safe_load(unified["path"].read_text(encoding="utf-8"))
    assert saved["presentation"]["time_format"] == "12"
    assert saved["webui"]["language"] == "pt-PT"


def test_disabled_credential_free_import_is_adopted_into_yaml(unified):
    unified["service"].synchronize()
    destination = DestinationStore(unified["database"]).create(
        unified["admin"],
        unified["admin"].user_id,
        "Imported webhook",
        "webhook",
        settings={"method": "POST"},
        shared=True,
        enabled=False,
    )
    RouteStore(unified["database"]).create(
        unified["admin"],
        unified["admin"].user_id,
        "Imported route",
        "generic",
        destination.id,
        enabled=False,
    )

    assert unified["service"].adopt_unmanaged_resources(unified["admin"]) == 2
    saved = yaml.safe_load(unified["path"].read_text(encoding="utf-8"))
    target = saved["outputs"]["webhook"]["imported_webhook"]
    assert target["enabled"] is False
    assert "secret" not in target
    assert saved["routing"]["generic"]["outputs"][0]["enabled"] is False


def test_nested_secrets_are_masked_without_hiding_token_metadata():
    masked = mask_secrets(
        {
            "outputs": {"webhook": {"ops": {"secret": {"url": "private"}}}},
            "api": {
                "tokens": {
                    "idrac": {
                        "token_sha256": "a" * 64,
                        "sources": ["dell_idrac"],
                    }
                }
            },
        }
    )
    assert masked["outputs"]["webhook"]["ops"]["secret"]["url"] == "<configured>"
    assert masked["api"]["tokens"]["idrac"]["token_sha256"] == "<configured>"
    assert masked["api"]["tokens"]["idrac"]["sources"] == ["dell_idrac"]
