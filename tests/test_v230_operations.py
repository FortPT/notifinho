"""v2.3 WebUI operations, notice visibility, and backup target contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

from api.security import hash_password
from models import Notification
from storage.backup_scheduler import BackupScheduler
from storage.backup_targets import BackupTargetStore
from storage.database import Database
from storage.delivery import DeliveryHistoryStore, DeliveryResult
from storage.destinations import DestinationStore
from storage.notices import NoticeStore
from storage.routes import RouteStore
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


def fast_hash(password: str) -> str:
    return hash_password(password, salt=b"\x23" * 16, iterations=1_000)


@pytest.fixture
def platform_state(tmp_path):
    now = [1_800_000_000]
    database = Database(tmp_path / "state" / "notifinho.db")
    database.migrate()
    users = UserStore(
        database,
        clock=lambda: now[0],
        password_hasher=fast_hash,
    )
    admin = users.bootstrap_admin("administrator", "correct horse battery staple")
    user = users.create("observer", "observer secure password")
    return now, database, users, admin, user


def test_first_login_is_notice_visibility_boundary(platform_state):
    now, database, users, admin, user = platform_state
    notices = NoticeStore(database, clock=lambda: now[0])
    notices.create(admin.actor, "Old maintenance", "Already completed", "warning")

    assert {item.name for item in notices.list_visible(user.actor)} == {
        "Notification operations",
        "Mounted configuration",
    }

    now[0] += 1
    assert users.authenticate("observer", "observer secure password") is not None
    now[0] += 1
    current = notices.create(admin.actor, "Current maintenance", "Starts soon", "warning")

    visible = {item.name for item in notices.list_visible(user.actor)}
    assert "Old maintenance" not in visible
    assert "Current maintenance" in visible

    changed = notices.update(
        admin.actor,
        current.id,
        name="Updated maintenance",
        message="Starts at 22:00",
        status="severe",
    )
    assert (changed.name, changed.status, changed.updated_at) == (
        "Updated maintenance",
        "severe",
        now[0],
    )
    notices.resolve(admin.actor, current.id)
    assert current.id not in {item.id for item in notices.list_visible(user.actor)}


def test_local_backup_target_write_test_and_manual_run(platform_state, tmp_path):
    _now, database, _users, admin, _user = platform_state
    destination = tmp_path / "external"
    configuration = Configuration({"platform": {"backups": {}}})
    targets = BackupTargetStore(database, configuration)
    target = targets.create(
        admin.actor,
        {
            "name": "Local archive",
            "type": "local",
            "local_path": str(destination),
            "enabled": True,
        },
    )

    tested = targets.test(admin.actor, target.id)
    assert tested.last_test_outcome == "success"
    assert tested.public()["mounted"] is True
    assert not list(destination.glob(".notifinho-write-test-*"))

    scheduler = BackupScheduler(database, configuration)
    result = scheduler.run_now(admin.actor, target.id)
    assert result["outcome"] == "success"
    mirrored = Path(result["external_path"])
    assert (mirrored / "manifest.json").is_file()


def test_remote_backup_target_masks_password_and_requires_mount_opt_in(
    platform_state,
):
    _now, database, _users, admin, _user = platform_state
    configuration = Configuration({"platform": {"backups": {"managed_mounts": False}}})
    target = BackupTargetStore(database, configuration).create(
        admin.actor,
        {
            "name": "SMB archive",
            "type": "smb",
            "host": "nas.fortpt.local",
            "share_name": "Backups",
            "remote_path": "Notifinho",
            "username": "backup-service",
            "password": "server-side-only",
            "enabled": True,
        },
    )

    public = target.public()
    assert public["credentials_configured"] is True
    assert "password" not in public
    assert "server-side-only" not in str(public)


def test_backup_target_conflict_does_not_rotate_secret(platform_state):
    _now, database, _users, admin, _user = platform_state
    targets = BackupTargetStore(database, Configuration({"platform": {}}))
    first = targets.create(
        admin.actor,
        {
            "name": "Primary SMB",
            "type": "smb",
            "host": "nas.fortpt.local",
            "share_name": "Backups",
            "username": "backup-service",
            "password": "original-secret",
        },
    )
    targets.create(
        admin.actor,
        {"name": "Duplicate name", "type": "local", "local_path": "/tmp/backups"},
    )

    with pytest.raises(ValueError, match="already configured"):
        targets.update(
            admin.actor,
            first.id,
            {"name": "Duplicate name", "password": "replacement-secret"},
        )

    secret_id = targets._secret_id(first.id)
    assert targets.secrets.resolve(admin.actor, secret_id) == b"original-secret"


def test_backup_target_protects_security_mount_options(platform_state):
    _now, database, _users, admin, _user = platform_state
    targets = BackupTargetStore(database, Configuration({"platform": {}}))
    with pytest.raises(ValueError, match="protected setting"):
        targets.create(
            admin.actor,
            {
                "name": "Unsafe NFS",
                "type": "nfs",
                "host": "nas.fortpt.local",
                "remote_path": "/exports/notifinho",
                "mount_options": "exec",
            },
        )


def test_shared_destination_history_and_metrics_are_visible_to_users(
    platform_state,
):
    _now, database, _users, admin, user = platform_state
    destination = DestinationStore(database).create(
        admin.actor,
        admin.id,
        "Shared Discord",
        "discord",
        shared=True,
    )
    route = RouteStore(database).create(
        admin.actor,
        admin.id,
        "Shared operations",
        "home_assistant",
        destination.id,
    )
    history = DeliveryHistoryStore(database, clock=lambda: 1_800_000_100)
    history.record(
        admin.id,
        "shared-delivery",
        route,
        Notification(
            source="home_assistant",
            title="Helpers error",
            body="One helper could not be loaded.",
            status="error",
            metadata={"_input_type": "HTTP", "device": "Infrastructure"},
        ),
        1,
        "delivered",
        DeliveryResult(True, response_status=204),
    )

    assert history.list_visible(user.actor, limit=25)[0].input_type == "HTTP"
    assert history.metrics(user.actor, 1_800_000_000)["requests"] == 1


def test_https_redirect_and_v230_webui_contract():
    service = WebUIService(
        Configuration({
            "webui": {
                "public_url": "https://notifinho.example.test",
                "enforce_https": True,
            }
        }),
        root=ROOT,
    )
    assert service.redirect_location("/", {}) == "https://notifinho.example.test/"
    assert service.redirect_location("/ui", {}) == "https://notifinho.example.test/ui"
    assert service.redirect_location("/", {"X-Forwarded-Proto": "https"}) is None

    markup = (ROOT / "src" / "webui" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "src" / "webui" / "app.js").read_text(encoding="utf-8")
    assert "Welcome back" not in markup
    assert 'id="view-inputs"' in markup and 'id="view-backups"' in markup
    assert 'id="backup-target-dialog"' in markup
    assert 'id="restart-dialog"' in markup
    assert '<th>Order</th>' not in markup
    assert 'actionButton("Send test", "test-destination-card"' in script
    assert 'state.auditPageSize = Number' in script
    assert 'toDataURL("image/png")' in script
    assert "Send a real test delivery?" not in script
    assert 'toast("Preview generated.")' not in script
