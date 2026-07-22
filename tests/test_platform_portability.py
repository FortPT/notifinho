"""Safe platform export, migration preview, and state backup tests."""

from __future__ import annotations

import json
import os
import threading

from pathlib import Path

import pytest

from api.security import hash_password
from storage.audit_events import AuditEventStore
from storage.backups import StateBackupStore
from storage.database import Database
from storage.destinations import DestinationStore
from storage.portability import PlatformPortabilityService
from storage.routes import RouteStore
from storage.secrets import SecretStore
from storage.sessions import SessionStore
from storage.users import UserStore


PASSWORD = "correct horse battery staple"


def fast_hash(password: str) -> str:
    return hash_password(password, salt=b"\x09" * 16, iterations=1_000)


@pytest.fixture
def platform_state(tmp_path):
    database = Database(tmp_path / "state" / "notifinho.db")
    database.migrate()
    users = UserStore(database, password_hasher=fast_hash)
    admin = users.bootstrap_admin("administrator", PASSWORD)
    owner = users.create("owner-user", "owner secure password")
    audit = AuditEventStore(database)
    secrets = SecretStore(database)
    destinations = DestinationStore(database, audit=audit)
    routes = RouteStore(database, audit=audit)
    portability = PlatformPortabilityService(
        database,
        secrets=secrets,
        audit=audit,
        clock=lambda: 1_750_000_000,
    )
    return {
        "database": database,
        "users": users,
        "admin": admin,
        "owner": owner,
        "audit": audit,
        "secrets": secrets,
        "destinations": destinations,
        "routes": routes,
        "portability": portability,
        "tmp_path": tmp_path,
    }


def seed_destination(state, *, owner=None, name="Primary Discord"):
    owner = owner or state["admin"]
    secret = state["secrets"].create(
        state["admin"].actor,
        owner.id,
        f"{name} credential",
        "discord_webhook",
        "https://discord.com/api/webhooks/123/private-value",
    )
    destination = state["destinations"].create(
        state["admin"].actor,
        owner.id,
        name,
        "discord",
        secret_id=secret.id,
        settings={"components_v2": True},
        shared=owner.id == state["admin"].id,
    )
    route = state["routes"].create(
        state["admin"].actor,
        owner.id,
        f"{name} route",
        "grafana",
        destination.id,
        filters={"hosts": ["monitor-*"]},
    )
    return secret, destination, route


def test_portable_export_never_contains_credentials_or_auth_material(platform_state):
    state = platform_state
    seed_destination(state)

    document = state["portability"].export_document(state["admin"].actor)
    encoded = json.dumps(document, sort_keys=True)

    assert document["schema"] == "notifinho.platform.v1"
    assert len(document["destinations"]) == 1
    assert len(document["routes"]) == 1
    assert document["destinations"][0]["secret_required"] is True
    for forbidden in (
        "private-value",
        "password_hash",
        "token_hash",
        "value_sha256",
        "secret_id",
        "file_name",
    ):
        assert forbidden not in encoded


def test_portable_import_requires_preview_fingerprint_and_disables_missing_secret(
    platform_state,
):
    state = platform_state
    document = {
        "schema": "notifinho.platform.v1",
        "destinations": [{
            "ref": "destination-1",
            "owner": "owner-user",
            "name": "Imported Slack",
            "output_type": "slack",
            "settings": {"include_metadata": True},
            "shared": False,
            "enabled": True,
            "secret_required": True,
        }],
        "routes": [{
            "owner": "owner-user",
            "name": "Imported Slack route",
            "source": "zabbix",
            "destination_ref": "destination-1",
            "filters": {"severities": ["warning"]},
            "priority": 100,
            "enabled": True,
        }],
    }
    plan = state["portability"].preview_document(state["admin"].actor, document)

    assert plan.valid is True
    assert plan.public()["destinations"][0]["secret_present"] is False
    assert "credential was intentionally not exported" in plan.warnings[0]
    with pytest.raises(ValueError, match="fingerprint"):
        state["portability"].apply_document(
            state["admin"].actor,
            document,
            "0" * 64,
        )
    result = state["portability"].apply_document(
        state["admin"].actor,
        document,
        plan.fingerprint,
    )
    destination = state["destinations"].list_visible(state["owner"].actor)[0]
    route = state["routes"].list_for_owner(
        state["owner"].actor,
        state["owner"].id,
    )[0]

    assert result["destinations_created"] == 1
    assert result["routes_created"] == 1
    assert destination.enabled is False
    assert destination.secret_configured is False
    assert route.enabled is False


def test_portable_preview_rejects_ownership_conflicts_and_duplicate_names(
    platform_state,
):
    state = platform_state
    document = {
        "schema": "notifinho.platform.v1",
        "destinations": [
            {
                "ref": reference,
                "owner": "administrator",
                "name": "Duplicate",
                "output_type": "teams",
                "settings": {},
                "shared": False,
                "enabled": True,
                "secret_required": False,
            }
            for reference in ("one", "two")
        ],
        "routes": [{
            "owner": "owner-user",
            "name": "Wrong owner route",
            "source": "grafana",
            "destination_ref": "one",
            "filters": {},
            "priority": 100,
            "enabled": True,
        }],
    }

    plan = state["portability"].preview_document(state["admin"].actor, document)

    assert plan.valid is False
    assert any("already exists" in item for item in plan.errors)
    assert any("owned or shared" in item for item in plan.errors)
    with pytest.raises(PermissionError):
        state["portability"].preview_document(state["owner"].actor, document)


def test_v1_yaml_preview_redacts_webhooks_and_imports_routes(platform_state):
    state = platform_state
    source = """
outputs:
  discord:
    enabled: true
    default:
      webhook: https://discord.com/api/webhooks/123/v1-private
    unused:
      webhook: PASTE_DISCORD_WEBHOOK_HERE
  teams:
    enabled: false
    default:
      webhook: https://example.webhook.office.com/v1-private
routing:
  grafana:
    outputs:
      - output: discord
        target: default
        match:
          hosts: [monitor-01]
      - output: teams
        target: default
"""
    plan = state["portability"].preview_v1_yaml(state["admin"].actor, source)
    public = json.dumps(plan.public(), sort_keys=True)

    assert plan.valid is True
    assert len(plan.destinations) == 2
    assert len(plan.routes) == 2
    assert "v1-private" not in public
    assert any("placeholder credential skipped" in item for item in plan.warnings)
    result = state["portability"].apply_v1_yaml(
        state["admin"].actor,
        source,
        plan.fingerprint,
    )
    destinations = state["destinations"].list_visible(state["admin"].actor)
    routes = state["routes"].list_for_owner(
        state["admin"].actor,
        state["admin"].id,
    )

    assert result["destinations_created"] == 2
    assert result["routes_created"] == 2
    assert all(item.secret_configured for item in destinations)
    assert {item.enabled for item in destinations} == {False, True}
    assert routes[0].filters["hosts"] == ("monitor-01",)


def test_failed_import_rolls_back_destinations_and_secret_files(
    platform_state,
    monkeypatch,
):
    state = platform_state
    source = """
outputs:
  discord:
    default:
      webhook: https://discord.com/api/webhooks/123/rollback-secret
routing:
  grafana:
    output: discord
    target: default
"""
    plan = state["portability"].preview_v1_yaml(state["admin"].actor, source)

    def fail(*_args, **_kwargs):
        raise RuntimeError("synthetic route failure")

    monkeypatch.setattr(state["portability"].routes, "create", fail)
    with pytest.raises(RuntimeError, match="synthetic"):
        state["portability"].apply_v1_yaml(
            state["admin"].actor,
            source,
            plan.fingerprint,
        )
    with state["database"].connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM destinations").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM secret_records").fetchone()[0] == 0
    assert list(state["secrets"].directory.iterdir()) == []


def test_state_backup_restores_database_and_secret_then_revokes_sessions(
    platform_state,
):
    state = platform_state
    secret, destination, _route = seed_destination(state)
    sessions = SessionStore(state["database"])
    sessions.create(state["admin"].id)
    backups = StateBackupStore(
        state["database"],
        audit=state["audit"],
        clock=lambda: 1_750_000_100,
    )
    backup = backups.create(state["admin"].actor)
    state["secrets"].rotate(
        state["admin"].actor,
        secret.id,
        "https://discord.com/api/webhooks/123/rotated-private",
    )
    state["destinations"].set_enabled(
        state["admin"].actor,
        destination.id,
        False,
    )

    with pytest.raises(ValueError, match="confirmation"):
        backups.restore(state["admin"].actor, backup.id, "wrong")
    result = backups.restore(state["admin"].actor, backup.id, backup.id)
    restored_secret = SecretStore(state["database"]).resolve(
        state["admin"].actor,
        secret.id,
    )
    restored_destination = DestinationStore(state["database"]).get(
        state["admin"].actor,
        destination.id,
    )
    with state["database"].connect() as connection:
        session_count = connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

    assert restored_secret.endswith(b"/private-value")
    assert restored_destination.enabled is True
    assert session_count == 0
    assert result["sessions_revoked"] is True
    assert result["safety_backup_id"] != backup.id
    assert len(backups.list(state["admin"].actor)) == 2
    with pytest.raises(PermissionError):
        backups.list(state["owner"].actor)


def test_state_backup_detects_tampering_and_ignores_unrecognized_directories(
    platform_state,
):
    state = platform_state
    seed_destination(state)
    backups = StateBackupStore(state["database"], audit=state["audit"])
    backup = backups.create(state["admin"].actor)
    path = backups.backup_directory / backup.id / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["files"]["notifinho.db"] = "0" * 64
    path.write_text(json.dumps(manifest), encoding="utf-8")
    os.chmod(path, 0o600)
    (backups.backup_directory / "untrusted-name").mkdir()

    assert backups.list(state["admin"].actor) == []
    with pytest.raises(RuntimeError, match="integrity"):
        backups.restore(state["admin"].actor, backup.id, backup.id)


def test_state_restore_swap_failure_rolls_back_live_database_and_secrets(
    platform_state,
    monkeypatch,
):
    state = platform_state
    secret, destination, _route = seed_destination(state)
    backups = StateBackupStore(state["database"], audit=state["audit"])
    backup = backups.create(state["admin"].actor)
    rotated_value = "https://discord.com/api/webhooks/123/live-after-backup"
    state["secrets"].rotate(state["admin"].actor, secret.id, rotated_value)
    state["destinations"].set_enabled(state["admin"].actor, destination.id, False)
    replace = os.replace

    def fail_staged_secret_install(source, target):
        source_path = Path(source)
        if (
            source_path.name == "secrets"
            and source_path.parent.name.startswith(".restore-")
        ):
            raise OSError("synthetic secret swap failure")
        return replace(source, target)

    monkeypatch.setattr("storage.backups.os.replace", fail_staged_secret_install)
    with pytest.raises(OSError, match="synthetic"):
        backups.restore(state["admin"].actor, backup.id, backup.id)

    live_destination = DestinationStore(state["database"]).get(
        state["admin"].actor,
        destination.id,
    )
    live_secret = SecretStore(state["database"]).resolve(
        state["admin"].actor,
        secret.id,
    )
    assert live_destination.enabled is False
    assert live_secret == rotated_value.encode()


def test_database_maintenance_blocks_concurrent_connections(platform_state):
    database = platform_state["database"]
    entered = threading.Event()

    def connect():
        with database.connect() as connection:
            connection.execute("SELECT 1").fetchone()
        entered.set()

    with database.maintenance():
        worker = threading.Thread(target=connect)
        worker.start()
        assert entered.wait(0.05) is False
    worker.join(timeout=2)

    assert entered.is_set()
