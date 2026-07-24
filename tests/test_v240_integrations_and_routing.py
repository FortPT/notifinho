"""v2.4 built-in integrations, input-aware routes, and safe YAML mutations."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from api.config_service import ConfigService
from api.schema import validate_config
from api.security import hash_password
from integrations.catalog import canonical_source, infer_input_type, integrations, route_options
from models import Notification
from storage.configuration_sync import UnifiedConfigurationService
from storage.database import Database
from storage.destinations import DestinationStore
from storage.secrets import SecretStore
from storage.ownership import Actor
from storage.routes import Route, RouteStore
from storage.users import UserStore
from storage.validation import ConflictError


PASSWORD = "correct horse battery staple"
TEAMS = "https://example.invalid/teams-hook"
DISCORD = "https://discord.com/api/webhooks/123/private"


class Configuration:
    def __init__(self, path: Path):
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
    return hash_password(password, salt=b"\x24" * 16, iterations=1_000)


def service(tmp_path, document):
    path = tmp_path / "config" / "config.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    path.chmod(0o600)
    configuration = Configuration(path)
    database = Database(tmp_path / "state" / "notifinho.db")
    assert database.migrate() == 8
    admin = UserStore(database, password_hasher=fast_hash).bootstrap_admin(
        "administrator", PASSWORD
    )
    sync = UnifiedConfigurationService(ConfigService(path, configuration), database)
    return path, database, admin.actor, sync


def base_document(tmp_path):
    return {
        "platform": {
            "enabled": True,
            "state_dir": str(tmp_path / "state"),
            "configuration_model": "unified_yaml_v1",
        },
        "webui": {"enabled": True},
        "outputs": {
            "teams": {
                "enabled": True,
                "operations": {
                    "name": "Operations",
                    "enabled": True,
                    "shared": True,
                    "webhook": TEAMS,
                },
            }
        },
        "routing": {},
    }


def test_catalogue_is_available_without_runtime_observation():
    items = {item["source"]: item for item in integrations()}
    assert len(items) >= 15
    assert [item["id"] for item in items["zabbix"]["inputs"]] == ["smtp", "http"]
    assert items["dell_idrac"]["inputs"] == [{"id": "redfish", "name": "Redfish"}]
    assert canonical_source("xen_orchestra") == "xo"
    assert infer_input_type("generic") == "http"
    labels = {item["label"] for item in route_options()}
    assert {
        "Zabbix (SMTP)",
        "Zabbix (HTTP)",
        "Generic (HTTP)",
        "Generic (Redfish)",
    } <= labels


def test_schema_rejects_duplicate_destination_display_names_before_sync(tmp_path):
    document = base_document(tmp_path)
    document["outputs"]["teams"]["operations_2"] = {
        "name": " operations ",
        "enabled": True,
        "webhook": TEAMS,
    }
    assert any(
        "duplicates another destination name" in error
        for error in validate_config(document)
    )


def test_duplicate_database_creation_does_not_modify_core_config(tmp_path):
    path, database, actor, sync = service(tmp_path, base_document(tmp_path))
    assert sync.synchronize().ready
    before = path.read_bytes()
    destinations = DestinationStore(database)
    with pytest.raises(ValueError, match="destination name is already configured"):
        destinations.create(
            actor,
            actor.user_id,
            " operations ",
            "teams",
            settings={},
            shared=True,
        )
    assert path.read_bytes() == before
    assert len(destinations.list_visible(actor)) == 1


def test_migration_preserves_effective_disabled_destination(tmp_path):
    document = base_document(tmp_path)
    document["outputs"]["teams"]["enabled"] = False
    document["outputs"]["teams"]["operations"]["enabled"] = True
    path, database, actor, sync = service(tmp_path, document)
    assert sync.synchronize().ready
    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "outputs" not in saved
    destination = DestinationStore(database).list_visible(actor)[0]
    assert destination.enabled is False


def test_database_destination_can_be_enabled_without_yaml_write(tmp_path):
    document = base_document(tmp_path)
    document["outputs"]["teams"]["enabled"] = False
    document["outputs"]["teams"]["operations"]["enabled"] = False
    path, database, actor, sync = service(tmp_path, document)
    assert sync.synchronize().ready
    before = path.read_bytes()
    destinations = DestinationStore(database)
    destination = destinations.list_visible(actor)[0]
    enabled = destinations.set_enabled(actor, destination.id, True)
    assert enabled.enabled is True
    assert path.read_bytes() == before


def test_destination_type_change_preserves_id_and_route_intent(tmp_path):
    path, database, actor, sync = service(tmp_path, base_document(tmp_path))
    assert sync.synchronize().ready
    before = path.read_bytes()
    destinations = DestinationStore(database)
    routes = RouteStore(database)
    destination = destinations.list_visible(actor)[0]
    route = routes.create(
        actor,
        actor.user_id,
        "Zabbix SMTP",
        "zabbix",
        destination.id,
        input_type="smtp",
        filters={"severities": ["critical"]},
        priority="normal",
        enabled=True,
    )
    secret = SecretStore(database).create(
        actor,
        actor.user_id,
        "Operations Discord",
        "discord-credentials",
        {"url": DISCORD},
    )
    destinations.set_secret(actor, destination.id, secret.id)
    changed = destinations.update(
        actor,
        destination.id,
        name="Operations Discord",
        output_type="discord",
        settings={"components_v2": True},
        enabled=True,
        shared=True,
    )
    assert changed.id == destination.id
    assert changed.output_type == "discord"
    mirrored_route = routes.get(actor, route.id)
    assert mirrored_route.destination_id == destination.id
    assert mirrored_route.source == "zabbix"
    assert mirrored_route.input_type == "smtp"
    assert path.read_bytes() == before


def test_legacy_source_metadata_and_home_lab_generic_are_removed(tmp_path):
    document = base_document(tmp_path)
    document["webui"].update(
        {
            "source_categories": {"dell_idrac": "hardware", "zabbix": "services"},
            "removed_sources": ["grafana"],
        }
    )
    document["routing"] = {
        "home_lab": {
            "outputs": [
                {
                    "name": "Home Lab Generic",
                    "output": "teams",
                    "target": "operations",
                    "enabled": True,
                }
            ]
        },
        "dell_idrac": {
            "outputs": [
                {
                    "name": "iDRAC hardware",
                    "output": "teams",
                    "target": "operations",
                    "enabled": True,
                }
            ]
        },
        "zabbix": {
            "outputs": [
                {
                    "name": "Zabbix alerts",
                    "output": "teams",
                    "target": "operations",
                    "enabled": True,
                }
            ]
        },
        "generic": {
            "outputs": [
                {
                    "name": "Generic API",
                    "output": "teams",
                    "target": "operations",
                    "enabled": True,
                }
            ]
        },
    }
    path, database, actor, sync = service(tmp_path, document)
    assert sync.synchronize().ready
    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "source_categories" not in saved["webui"]
    assert "removed_sources" not in saved["webui"]
    assert "routing" not in saved
    routes = RouteStore(database).list_visible(actor)
    assert all(item.name != "Home Lab Generic" for item in routes)
    assert next(item for item in routes if item.name == "Generic API").source == "*"
    assert next(item for item in routes if item.name == "Generic API").input_type == "http"
    assert next(item for item in routes if item.name == "iDRAC hardware").input_type == "redfish"
    assert next(item for item in routes if item.name == "Zabbix alerts").input_type == "smtp"
    assert sync.source_categories() == {
        "dell_idrac": "hardware",
        "zabbix": "monitoring",
    }


def test_route_matching_distinguishes_integration_input():
    base = dict(
        id="a" * 32,
        owner_user_id="b" * 32,
        destination_id="c" * 32,
        name="route",
        source="zabbix",
        filters={},
        priority=50,
        enabled=True,
        created_at=1,
        updated_at=1,
    )
    smtp = Route(**base, input_type="smtp")
    http_values = dict(base)
    http_values["id"] = "d" * 32
    http = Route(**http_values, input_type="http")
    notification = Notification(
        source="zabbix",
        title="Test",
        metadata={"_input_type": "SMTP"},
    )
    assert RouteStore.matches(smtp, notification)
    assert not RouteStore.matches(http, notification)


def test_config_replacement_preserves_mode(tmp_path):
    document = base_document(tmp_path)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    path.chmod(0o640)
    configuration = Configuration(path)
    service = ConfigService(path, configuration)
    candidate = service.snapshot()
    candidate.setdefault("presentation", {})["time_format"] = "24"
    service.replace(candidate)
    assert path.stat().st_mode & 0o777 == 0o640
