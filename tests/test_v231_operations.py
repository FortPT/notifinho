"""v2.3.1 corrective WebUI and HTTP-login contracts."""

from pathlib import Path

import yaml

from api.config_service import ConfigService
from api.schema import validate_config
from api.security import hash_password
from storage.configuration_sync import UnifiedConfigurationService
from storage.database import Database
from storage.users import UserStore
from webui.service import WebUIService


ROOT = Path(__file__).resolve().parents[1]


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


class ReloadableConfiguration(Configuration):
    def __init__(self, path):
        self.path = Path(path)
        self.reload()

    def reload(self):
        self.data = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}


def fast_hash(password: str) -> str:
    return hash_password(password, salt=b"\x31" * 16, iterations=1_000)


def test_http_login_is_available_unless_https_enforcement_is_explicit():
    direct = WebUIService(
        Configuration({
            "webui": {"public_url": "https://notifinho.example.test"},
            "platform": {"secure_cookies": False},
        }),
        root=ROOT,
    )
    assert direct.redirect_location("/", {}) is None

    enforced = WebUIService(
        Configuration({
            "webui": {
                "public_url": "https://notifinho.example.test",
                "enforce_https": True,
            },
            "platform": {"secure_cookies": True},
        }),
        root=ROOT,
    )
    assert enforced.redirect_location("/", {}) == "https://notifinho.example.test/"


def test_source_category_configuration_is_bounded():
    valid = {
        "webui": {
            "source_categories": {
                "grafana": "applications",
                "home_assistant": "controllers",
            }
        }
    }
    assert validate_config(valid) == []
    assert validate_config({
        "webui": {"source_categories": {"grafana": "unknown"}}
    }) == ["webui.source_categories contains an invalid category"]


def test_source_category_update_persists_in_authoritative_yaml(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "platform:\n"
        "  configuration_model: unified_yaml_v1\n"
        "webui:\n"
        "  enabled: true\n"
        "  source_categories: {}\n",
        encoding="utf-8",
    )
    runtime = ReloadableConfiguration(path)
    database = Database(tmp_path / "state" / "notifinho.db")
    database.migrate()
    users = UserStore(database, password_hasher=fast_hash)
    admin = users.bootstrap_admin(
        "administrator",
        "correct horse battery staple",
    )
    service = UnifiedConfigurationService(
        ConfigService(path, runtime),
        database,
    )

    categories = service.update_source_category(
        admin.actor,
        "grafana",
        "applications",
    )

    assert categories == {"grafana": "applications"}
    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert saved["webui"]["source_categories"] == {
        "grafana": "applications",
    }


def test_v231_webui_removes_old_header_and_exposes_corrective_controls():
    markup = (ROOT / "src" / "webui" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "src" / "webui" / "app.js").read_text(encoding="utf-8")
    styles = (ROOT / "src" / "webui" / "styles.css").read_text(encoding="utf-8")

    assert 'id="connection-state"' not in markup
    assert 'id="refresh-button"' not in markup
    assert 'id="logout-button"' not in markup
    assert 'id="profile-menu-popover"' in markup
    assert 'data-action="logout"' in markup
    assert 'id="view-sources"' in markup
    assert 'id="view-updates"' in markup
    assert "Notify every user" not in markup
    assert ">Active Sources<" in markup
    assert ">Active Destinations<" in markup
    assert ">Active Routes<" in markup
    assert "<th>Input</th>" in markup
    assert markup.index('id="audit-table"') < markup.index('id="audit-page-size"')
    assert "Shown in Routing Flow" not in script
    assert 'const form = event.currentTarget;' in script
    assert "form.reset();" in script
    assert '"Home Assistant API"' in script
    assert '"Supermicro Redfish"' in script
    assert 'semanticInformation ? "information"' in script
    assert "createImageBitmap" in script and "readAsDataURL" in script
    assert ".flow-row.disabled .flow-arrow" in styles
    assert "animation: none" in styles
    assert ".flow-row.problem .flow-arrow" in styles
    assert "@keyframes route-error" in styles
    assert ".timeline-item.information" in styles


def test_remote_target_save_enables_managed_mounting_before_creation():
    script = (ROOT / "src" / "webui" / "app.js").read_text(encoding="utf-8")
    enable = script.index('if (type !== "local" && !state.managedMounts)')
    settings = script.index('request("/backup-settings"', enable)
    target = script.index("await request(id ? `/backup-targets/${id}`", settings)
    assert enable < settings < target
