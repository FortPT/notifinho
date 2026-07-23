"""v2.2 operational notices, presentation, history, and backup contracts."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from api.security import hash_password
from models import Notification
from storage.api_tokens import APITokenStore
from storage.backup_scheduler import BackupScheduler
from storage.database import Database
from storage.delivery import DeliveryHistoryStore, DeliveryResult
from storage.destinations import DestinationStore
from storage.health import HealthCheckService
from storage.notices import NoticeStore
from storage.ownership import Actor
from storage.routes import RouteStore, route_priority_name, route_priority_value
from storage.users import UserStore


def fast_hash(password: str) -> str:
    return hash_password(password, salt=b"\x0e" * 16, iterations=1_000)


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


@pytest.fixture
def operations(tmp_path):
    database = Database(tmp_path / "state" / "notifinho.db")
    database.migrate()
    users = UserStore(database, password_hasher=fast_hash)
    admin = users.bootstrap_admin("administrator", "correct horse battery staple")
    user = users.create("observer", "observer secure password")
    return database, users, admin, user


def test_notices_are_dismissed_per_user_and_system_notices_resolve(operations):
    database, _users, admin, user = operations
    with database.transaction() as connection:
        connection.execute(
            "UPDATE users SET first_login_at = ? WHERE id IN (?, ?)",
            (1_699_999_999, user.id, admin.id),
        )
    store = NoticeStore(database, clock=lambda: 1_700_000_000)
    announcement = store.create(admin.actor, "Maintenance", "Starts at 22:00", "warning")

    assert {item.name for item in store.list_visible(user.actor)} >= {
        "Maintenance",
        "Notification operations",
        "Mounted configuration",
    }
    store.dismiss(user.actor, announcement.id)
    assert announcement.id not in {item.id for item in store.list_visible(user.actor)}
    assert announcement.id in {item.id for item in store.list_visible(admin.actor)}

    store.sync_system(
        "synthetic-error",
        "Synthetic failure",
        "Repair the synthetic fault.",
        status="severe",
        kind="system_error",
        persistent=True,
        active=True,
    )
    persistent = next(item for item in store.list_visible(user.actor) if item.name == "Synthetic failure")
    with pytest.raises(PermissionError, match="remain until resolved"):
        store.dismiss(user.actor, persistent.id)
    store.sync_system(
        "synthetic-error",
        "Synthetic failure",
        "Healthy.",
        status="severe",
        kind="system_error",
        persistent=True,
        active=False,
    )
    assert persistent.id not in {item.id for item in store.list_visible(user.actor)}


def test_profile_picture_is_validated_and_application_status_is_enforced(operations):
    database, users, admin, user = operations
    png = "data:image/png;base64,iVBORw0KGgo="
    assert users.set_avatar(user.id, png).avatar_data == png
    assert users.set_avatar(user.id, None).avatar_data is None
    with pytest.raises(ValueError, match="does not match"):
        users.set_avatar(user.id, "data:image/png;base64,AAAA")

    tokens = APITokenStore(database)
    created = tokens.create(
        admin.actor,
        user.id,
        "Camera application",
        source_scopes=["camera"],
    )
    assert tokens.authenticate(created.value, "camera") is not None
    tokens.set_enabled(admin.actor, created.token.id, False)
    assert tokens.authenticate(created.value, "camera") is None
    tokens.delete(admin.actor, created.token.id)
    with pytest.raises(KeyError):
        tokens.get(admin.actor, created.token.id)


def test_delivery_history_tracks_device_event_input_and_range_metrics(operations):
    database, _users, admin, _user = operations
    destination = DestinationStore(database).create(
        admin.actor,
        admin.id,
        "Discord operations",
        "discord",
        settings={"channel_name": "alerts"},
        shared=True,
    )
    route = RouteStore(database).create(
        admin.actor,
        admin.id,
        "Critical cameras",
        "home_assistant",
        destination.id,
        priority="critical",
    )
    notification = Notification(
        source="home_assistant",
        title="Camera unavailable",
        body="The camera integration did not answer.",
        status="error",
        metadata={
            "_input_type": "HTTP",
            "device": "CAM-01",
            "event_name": "Integration unavailable",
            "severity": "critical",
            "status": "error",
        },
    )
    history = DeliveryHistoryStore(database, clock=lambda: 1_700_000_000)
    attempt = history.record(
        admin.id,
        "delivery-1",
        route,
        notification,
        1,
        "delivered",
        DeliveryResult(True, response_status=204),
    )

    assert (attempt.device_name, attempt.event_name, attempt.input_type) == (
        "CAM-01",
        "Integration unavailable",
        "HTTP",
    )
    assert attempt.event_description == "The camera integration did not answer."
    assert history.metrics(admin.actor, 1_699_999_000) == {
        "requests": 1,
        "delivered": 1,
        "success_percent": 100,
        "observed_sources": 1,
    }
    assert route_priority_value("high") == 25
    assert route_priority_name(route.priority) == "critical"


def test_health_checks_report_missing_destination_credentials(operations):
    database, _users, admin, _user = operations
    DestinationStore(database).create(
        admin.actor,
        admin.id,
        "Unconfigured Discord",
        "discord",
        shared=True,
    )
    checks = HealthCheckService(database, None, clock=lambda: 1_700_000_000).run()
    credentials = next(item for item in checks if item["key"] == "destination_credentials")
    assert credentials["status"] == "error"
    assert "Unconfigured Discord" in credentials["detail"]


def test_scheduled_backup_runs_once_and_mirrors_to_host_mount(operations, tmp_path):
    database, _users, _admin, _user = operations
    external = tmp_path / "mounted-share"
    external.mkdir()
    instant = datetime(2026, 7, 22, 3, 0, tzinfo=timezone.utc).timestamp()
    configuration = Configuration({
        "presentation": {"timezone": "UTC"},
        "platform": {
            "backups": {
                "schedule": "daily",
                "time": "02:00",
                "external_enabled": True,
                "external_type": "nfs",
                "external_path": str(external),
            }
        },
    })
    scheduler = BackupScheduler(database, configuration, clock=lambda: instant)

    result = scheduler.run_due(instant)
    assert result is not None and result["outcome"] == "success"
    assert scheduler.run_due(instant) is None
    mirrored = external / "notifinho-state-backups" / result["backup_id"]
    assert (mirrored / "manifest.json").is_file()
    assert scheduler.last_run()["outcome"] == "success"
