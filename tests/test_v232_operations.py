"""v2.3.2 source, session, destination-test, and managed-mount regressions."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import yaml

from api.config_service import ConfigService
from api.platform import PlatformAPI
from api.schema import validate_config
from api.security import hash_password
from storage.backup_targets import BackupTarget, BackupTargetStore
from storage.configuration_sync import UnifiedConfigurationService
from storage.database import Database
from storage.ownership import Actor
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
    return hash_password(password, salt=b"\x32" * 16, iterations=1_000)


def configuration_service(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "platform:\n"
        "  configuration_model: unified_yaml_v1\n"
        "webui:\n"
        "  enabled: true\n"
        "  source_categories:\n"
        "    old_source: services\n"
        "  removed_sources: []\n",
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
    return path, service, admin.actor


def test_cookie_selection_prefers_the_configured_http_or_https_mode():
    api = PlatformAPI.__new__(PlatformAPI)
    api.configuration = Configuration(
        {"platform": {"secure_cookies": False}}
    )
    headers = {
        "Cookie": (
            "__Host-notifinho_session=old-secure; "
            "notifinho_session=current-standard"
        )
    }
    assert api._session_token(headers) == "current-standard"

    api.configuration.data["platform"]["secure_cookies"] = True
    assert api._session_token(headers) == "old-secure"


def test_source_categories_migrate_legacy_values_and_removal_is_persistent(
    tmp_path,
):
    path, service, actor = configuration_service(tmp_path)

    assert service.source_categories() == {"old_source": "monitoring"}
    service.remove_source(actor, "old_source")
    assert service.source_categories() == {}
    assert service.removed_sources() == ["old_source"]

    categories = service.update_source_category(
        actor,
        "old_source",
        "virtualization",
    )
    assert categories == {"old_source": "virtualization"}
    assert service.removed_sources() == []

    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert saved["webui"]["source_categories"] == {
        "old_source": "virtualization",
    }
    assert saved["webui"]["removed_sources"] == []


def test_source_removal_rejects_enabled_exact_and_wildcard_routes():
    actor = Actor("admin-user", "admin")

    class Sync:
        def __init__(self, routes):
            self.routes = routes
            self.removed = []

        def list_routes(self, _actor):
            return self.routes

        def remove_source(self, _actor, source):
            self.removed.append(source)

        def source_categories(self):
            return {}

        def removed_sources(self):
            return self.removed

    api = PlatformAPI.__new__(PlatformAPI)
    api.configuration_sync = Sync([
        SimpleNamespace(source="*", enabled=True),
    ])
    try:
        api._source_categories_endpoint(
            "DELETE",
            {"source": "dell_idrac"},
            actor,
        )
    except ValueError as error:
        assert "active sources" in str(error)
    else:
        raise AssertionError("enabled wildcard route must block source removal")

    api.configuration_sync = Sync([
        SimpleNamespace(source="dell_idrac", enabled=False),
    ])
    response = api._source_categories_endpoint(
        "DELETE",
        {"source": "dell_idrac"},
        actor,
    )
    assert response.status == 200
    assert response.payload["removed_sources"] == ["dell_idrac"]


def test_nfs_managed_mount_disables_nlm_for_read_only_container(tmp_path):
    commands = []

    def runner(command, **_kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    store = BackupTargetStore.__new__(BackupTargetStore)
    store.runner = runner
    target = BackupTarget(
        id="a" * 32,
        owner_user_id="admin-user",
        name="UNAS backups",
        target_type="nfs",
        host="192.168.0.163",
        remote_path="/var/nfs/shared/Backups/Notifinho",
        share_name="",
        local_path=str(tmp_path / "mount"),
        username="",
        domain="",
        credentials_configured=False,
        mount_options="vers=3",
        enabled=True,
        mounted_at=None,
        last_test_at=None,
        last_test_outcome=None,
        last_error=None,
        created_at=1,
        updated_at=1,
    )

    store._mount(Actor("admin-user", "admin"), target, tmp_path / "mount")

    assert commands == [[
        "mount",
        "-t",
        "nfs",
        "-o",
        "rw,nosuid,nodev,noexec,nolock,vers=3",
        "192.168.0.163:/var/nfs/shared/Backups/Notifinho",
        str(tmp_path / "mount"),
    ]]


def test_managed_mount_override_contains_the_verified_capability_set():
    override = yaml.safe_load(
        (ROOT / "compose.managed-backups.yaml").read_text(encoding="utf-8")
    )
    service = override["services"]["notifinho"]
    assert service["user"] == "0:0"
    assert set(service["cap_add"]) == {
        "DAC_OVERRIDE",
        "FOWNER",
        "SYS_ADMIN",
    }


def test_v232_webui_uses_vendor_icons_safe_removal_and_header_restart():
    markup = (ROOT / "src" / "webui" / "index.html").read_text(
        encoding="utf-8"
    )
    script = (ROOT / "src" / "webui" / "app.js").read_text(
        encoding="utf-8"
    )
    service = WebUIService(Configuration({}), root=ROOT)

    assert 'id="restart-header-button"' in markup
    settings = markup[
        markup.index('id="view-settings"'):
        markup.index('id="view-updates"')
    ]
    assert "Restart Notifinho" not in settings
    assert "<th>Category</th>" in markup
    assert "<th>Management</th>" in markup
    assert 'actionButton("Remove", "remove-source"' in script
    assert 'route.source === source || route.source === "*"' in script
    assert 'source: "notifinho"' in script
    assert 'source: "home_assistant"' not in script[
        script.index("function cardSampleEvent"):
        script.index("async function runPreview")
    ]
    assert "SOURCE_ICONS" in script
    assert "GENERIC_SOURCE_ICON" in script
    response = service.response("/ui/source-icons/unifi-drive.png")
    assert response is not None and response.status == 200
    assert response.content_type == "image/png"


def test_removed_source_schema_is_bounded():
    assert validate_config({
        "webui": {
            "source_categories": {"grafana": "monitoring"},
            "removed_sources": ["retired_source"],
        }
    }) == []
    assert validate_config({
        "webui": {
            "removed_sources": "retired_source",
        }
    }) == ["webui.removed_sources must be a list of source names"]
