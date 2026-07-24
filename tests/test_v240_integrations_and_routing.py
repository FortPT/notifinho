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
    assert database.migrate() == 7
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


def test_duplicate_creation_does_not_modify_config(tmp_path):
    path, _database, actor, sync = service(tmp_path, base_document(tmp_path))
    assert sync.synchronize().ready
    before = path.read_bytes()
    with pytest.raises(ConflictError, match='A destination named "operations"'):
        sync.create_destination(
            actor,
            {
                "name": "operations",
                "output_type": "teams",
                "settings": {},
                "secret": {"url": TEAMS},
                "enabled": True,
            },
        )
    assert path.read_bytes() == before
    assert len(sync.list_destinations(actor)) == 1


def test_enabled_destination_enables_parent_output_group(tmp_path):
    document = base_document(tmp_path)
    document["outputs"]["teams"]["enabled"] = False
    document["outputs"]["teams"]["operations"]["enabled"] = False
    path, _database, actor, sync = service(tmp_path, document)
    assert sync.synchronize().ready
    created = sync.create_destination(
        actor,
        {
            "name": "Hardware",
            "output_type": "teams",
            "settings": {},
            "secret": {"url": TEAMS},
            "enabled": True,
        },
    )
    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert saved["outputs"]["teams"]["enabled"] is True
    assert created.enabled is True


def test_enabling_existing_destination_enables_parent_group(tmp_path):
    document = base_document(tmp_path)
    document["outputs"]["teams"]["enabled"] = False
    document["outputs"]["teams"]["operations"]["enabled"] = False
    path, _database, actor, sync = service(tmp_path, document)
    assert sync.synchronize().ready
    destination = sync.list_destinations(actor)[0]
    assert destination.enabled is False

    enabled = sync.update_destination(actor, destination.id, {"enabled": True})
    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert saved["outputs"]["teams"]["enabled"] is True
    assert saved["outputs"]["teams"]["operations"]["enabled"] is True
    assert enabled.enabled is True


def test_destination_type_change_preserves_id_and_route_intent(tmp_path):
    path, _database, actor, sync = service(tmp_path, base_document(tmp_path))
    assert sync.synchronize().ready
    destination = sync.list_destinations(actor)[0]
    route = sync.create_route(
        actor,
        {
            "name": "Zabbix SMTP",
            "source": "zabbix",
            "input_type": "smtp",
            "destination_id": destination.id,
            "filters": {"severities": ["critical"]},
            "priority": "normal",
            "enabled": True,
        },
    )
    changed = sync.update_destination(
        actor,
        destination.id,
        {
            "name": "Operations Discord",
            "output_type": "discord",
            "settings": {"components_v2": True},
            "secret": {"url": DISCORD},
            "enabled": True,
            "shared": True,
        },
    )
    assert changed.id == destination.id
    assert changed.output_type == "discord"
    mirrored_route = next(item for item in sync.list_routes(actor) if item.id == route.id)
    assert mirrored_route.destination_id == destination.id
    assert mirrored_route.source == "zabbix"
    assert mirrored_route.input_type == "smtp"
    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
    entry = saved["routing"]["zabbix"]["outputs"][0]
    assert entry["input"] == "smtp"
    assert entry["output"] == "discord"
    assert entry["target"] == "operations_discord"
    assert "teams" not in saved["outputs"]


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
    path, _database, actor, sync = service(tmp_path, document)
    assert sync.synchronize().ready
    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "source_categories" not in saved["webui"]
    assert "removed_sources" not in saved["webui"]
    assert "home_lab" not in saved["routing"]
    assert "generic" not in saved["routing"]
    assert saved["routing"]["*"]["outputs"][0]["input"] == "http"
    assert saved["routing"]["dell_idrac"]["outputs"][0]["input"] == "redfish"
    assert saved["routing"]["zabbix"]["outputs"][0]["input"] == "smtp"
    assert sync.source_categories() == {
        "dell_idrac": "hardware",
        "zabbix": "monitoring",
    }
    assert all(item.name != "Home Lab Generic" for item in sync.list_routes(actor))


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
