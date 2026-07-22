"""Persistent v2 platform database and ownership-contract tests."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys

from pathlib import Path

import pytest

from storage.database import Database
from storage.migrations import LATEST_SCHEMA_VERSION
from storage.migrations import MIGRATIONS
from storage.ownership import Actor, OwnershipPolicy
from storage.runtime import initialize_state, state_directory


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


def test_database_migration_is_idempotent_and_records_all_foundation_tables(tmp_path):
    database = Database(tmp_path / "state" / "notifinho.db")

    assert database.migrate() == LATEST_SCHEMA_VERSION
    assert database.migrate() == LATEST_SCHEMA_VERSION

    with database.connect() as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        migration = connection.execute(
            "SELECT version, name FROM schema_migrations"
        ).fetchone()
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]

    assert {
        "users",
        "sessions",
        "api_tokens",
        "secret_records",
        "destinations",
        "routes",
        "audit_events",
        "delivery_attempts",
    } <= tables
    assert (migration["version"], migration["name"]) == (
        1,
        "platform foundation",
    )
    assert foreign_keys == 1


def test_database_and_parent_are_owner_only(tmp_path):
    database = Database(tmp_path / "state" / "notifinho.db")
    database.migrate()

    assert database.path.parent.stat().st_mode & 0o777 == 0o700
    assert database.path.stat().st_mode & 0o777 == 0o600


def test_database_rejects_symlink_file_and_directory(tmp_path):
    target_directory = tmp_path / "target"
    target_directory.mkdir()
    linked_directory = tmp_path / "linked"
    linked_directory.symlink_to(target_directory, target_is_directory=True)
    with pytest.raises(ValueError, match="directory"):
        Database(linked_directory / "notifinho.db").migrate()

    real_database = tmp_path / "real.db"
    real_database.write_bytes(b"")
    linked_database = tmp_path / "linked.db"
    linked_database.symlink_to(real_database)
    with pytest.raises(ValueError, match="file"):
        Database(linked_database).migrate()


def test_database_rejects_newer_schema(tmp_path):
    database = Database(tmp_path / "state" / "notifinho.db")
    database.migrate()
    with database.connect() as connection:
        connection.execute(f"PRAGMA user_version = {LATEST_SCHEMA_VERSION + 1}")

    with pytest.raises(RuntimeError, match="newer than supported"):
        database.migrate()


def test_database_foreign_keys_protect_owned_records(tmp_path):
    database = Database(tmp_path / "state" / "notifinho.db")
    database.migrate()
    with pytest.raises(sqlite3.IntegrityError):
        with database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO sessions(
                    id, user_id, token_hash, csrf_hash, created_at,
                    last_seen_at, expires_at, idle_expires_at
                ) VALUES ('session', 'missing', 'token', 'csrf', 1, 1, 2, 2)
                """
            )


def test_state_initialization_is_opt_in_and_supports_environment_override(
    monkeypatch,
    tmp_path,
):
    disabled = Configuration({"platform": {"enabled": False}})
    monkeypatch.setenv("NOTIFINHO_STATE_DIR", str(tmp_path / "disabled"))
    assert initialize_state(disabled) is None
    assert not (tmp_path / "disabled").exists()

    enabled = Configuration({"platform": {"enabled": True}})
    database = initialize_state(enabled)
    assert database is not None
    assert database.path == tmp_path / "disabled" / "notifinho.db"
    assert database.schema_version == LATEST_SCHEMA_VERSION


def test_state_directory_requires_a_bounded_absolute_path(monkeypatch):
    configuration = Configuration({"platform": {"state_dir": "relative/state"}})
    monkeypatch.delenv("NOTIFINHO_STATE_DIR", raising=False)
    with pytest.raises(ValueError, match="absolute"):
        state_directory(configuration)

    monkeypatch.setenv("NOTIFINHO_STATE_DIR", "/")
    with pytest.raises(ValueError, match="filesystem root"):
        state_directory(configuration)


def test_ownership_policy_keeps_private_resources_private():
    owner = Actor("owner", "user")
    another = Actor("another", "user")
    admin = Actor("admin", "admin")

    assert OwnershipPolicy.can_read(owner, "owner") is True
    assert OwnershipPolicy.can_write(owner, "owner") is True
    assert OwnershipPolicy.can_read(another, "owner") is False
    assert OwnershipPolicy.can_read(another, "owner", shared=True) is True
    assert OwnershipPolicy.can_write(another, "owner") is False
    assert OwnershipPolicy.can_read(admin, "owner") is True
    assert OwnershipPolicy.can_write(admin, "owner") is True
    assert OwnershipPolicy.can_read(None, "owner", shared=True) is False

    with pytest.raises(PermissionError):
        OwnershipPolicy.require_write(another, "owner")


def test_account_cli_initializes_state_and_bootstraps_admin(tmp_path):
    root = Path(__file__).resolve().parents[1]
    state = tmp_path / "cli-state"
    environment = os.environ.copy()
    environment["SYNTHETIC_PASSWORD"] = "correct horse battery staple"

    initialized = subprocess.run(
        [
            sys.executable,
            str(root / "tools" / "manage_users.py"),
            "--state-dir",
            str(state),
            "init",
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    created = subprocess.run(
        [
            sys.executable,
            str(root / "tools" / "manage_users.py"),
            "--state-dir",
            str(state),
            "create-admin",
            "--username",
            "administrator",
            "--password-env",
            "SYNTHETIC_PASSWORD",
        ],
        cwd=root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    listed = subprocess.run(
        [
            sys.executable,
            str(root / "tools" / "manage_users.py"),
            "--state-dir",
            str(state),
            "list-users",
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )

    assert f"state_schema={LATEST_SCHEMA_VERSION}" in initialized.stdout
    assert "account_created=admin" in created.stdout
    assert "administrator\trole=admin\tenabled=true" in listed.stdout


def test_schema_one_database_upgrades_to_user_routing_schema(tmp_path):
    database = Database(tmp_path / "state" / "notifinho.db")
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at INTEGER NOT NULL DEFAULT (unixepoch())
            )
            """
        )
        version, name, statements = MIGRATIONS[0]
        for statement in statements:
            connection.execute(statement)
        connection.execute(
            "INSERT INTO schema_migrations(version, name) VALUES (?, ?)",
            (version, name),
        )
        connection.execute("PRAGMA user_version = 1")
        connection.commit()

    assert database.migrate() == LATEST_SCHEMA_VERSION
    with database.connect() as connection:
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(api_tokens)")
        }
        migration = connection.execute(
            "SELECT name FROM schema_migrations WHERE version = 2"
        ).fetchone()[0]
        bootstrap_migration = connection.execute(
            "SELECT name FROM schema_migrations WHERE version = 3"
        ).fetchone()[0]
        configuration_migration = connection.execute(
            "SELECT name FROM schema_migrations WHERE version = 4"
        ).fetchone()[0]
        destination_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(destinations)")
        }
    assert {"version", "updated_at"} <= columns
    assert migration == "user routing and delivery foundation"
    assert bootstrap_migration == "secure first-run bootstrap"
    assert configuration_migration == "unified YAML configuration mirror"
    assert "configuration_key" in destination_columns
    assert len(list((database.path.parent / "schema-backups").glob("*.db"))) == 1


def test_missing_platform_switch_enables_persistent_legacy_config_fallback(
    monkeypatch,
    tmp_path,
):
    monkeypatch.delenv("NOTIFINHO_STATE_DIR", raising=False)
    monkeypatch.setattr(
        "storage.runtime.DEFAULT_STATE_DIRECTORY",
        str(tmp_path / "config" / "platform-state"),
    )

    database = initialize_state(Configuration({}))

    assert database is not None
    assert database.path == tmp_path / "config" / "platform-state" / "notifinho.db"
    assert database.schema_version == LATEST_SCHEMA_VERSION


def test_implicit_platform_state_failure_preserves_legacy_pipeline(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        "storage.runtime.Database.migrate",
        lambda _database: (_ for _ in ()).throw(PermissionError("read only")),
    )

    assert initialize_state(Configuration({})) is None
    assert "legacy notification pipeline will continue" in capsys.readouterr().err

    with pytest.raises(PermissionError, match="read only"):
        initialize_state(Configuration({"platform": {"enabled": True}}))
