"""v2.5 database-authoritative resources and normalized configuration contract."""

from pathlib import Path

import yaml

from api.schema import validate_config
from storage.migrations import LATEST_SCHEMA_VERSION


ROOT = Path(__file__).resolve().parents[1]


def test_schema_8_adds_isolated_settings_records():
    migrations = (ROOT / "src/storage/migrations.py").read_text(encoding="utf-8")
    assert LATEST_SCHEMA_VERSION == 8
    assert "CREATE TABLE settings_records" in migrations
    assert "PRIMARY KEY(namespace, setting_key)" in migrations


def test_example_configuration_contains_only_process_bootstrap_settings():
    path = ROOT / "config/config.example.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert validate_config(document) == []
    assert document["platform"]["configuration_model"] == "platform_database_v1"
    for section in (
        "outputs",
        "routing",
        "notifications",
        "presentation",
        "home_assistant",
        "redfish",
    ):
        assert section not in document
    assert "tokens" not in document["api"]
    assert "backups" not in document["platform"]
    assert "language" not in document["webui"]


def test_database_model_rejects_reintroduced_webui_managed_yaml_sections():
    document = yaml.safe_load(
        (ROOT / "config/config.example.yaml").read_text(encoding="utf-8")
    )
    document["routing"] = {}
    document["api"]["tokens"] = {}
    errors = validate_config(document)
    assert "routing is database-managed; edit routes in the WebUI" in errors
    assert "api.tokens is database-managed; edit applications in the WebUI" in errors


def test_webui_exposes_every_migrated_integration_setting():
    markup = (ROOT / "src/webui/index.html").read_text(encoding="utf-8")
    script = (ROOT / "src/webui/app.js").read_text(encoding="utf-8")
    assert 'id="integration-settings-list"' in markup
    assert 'id="integration-settings-dialog"' in markup
    assert 'request("/integration-settings")' in script
    for source in (
        "xo",
        "zabbix",
        "dell_idrac",
        "unifi_protect",
        "home_assistant",
        "redfish",
    ):
        assert source in script
    assert "Deduplication window" in script
    assert "Trusted client IP addresses" in script
    assert "Device aliases" in script
    assert "Endpoint aliases" in script
