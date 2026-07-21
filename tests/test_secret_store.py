"""Owner-scoped, non-revealing secret storage tests."""

from __future__ import annotations

import os

import pytest

from api.security import hash_password
from storage.database import Database
from storage.ownership import Actor
from storage.secrets import SecretStore
from storage.users import UserStore


def fast_hash(password: str) -> str:
    return hash_password(password, salt=b"\x02" * 16, iterations=1_000)


@pytest.fixture
def vault(tmp_path):
    database = Database(tmp_path / "state" / "notifinho.db")
    database.migrate()
    users = UserStore(database, password_hasher=fast_hash)
    admin = users.bootstrap_admin("administrator", "correct horse battery staple")
    owner = users.create("operator", "operator secure password")
    another = users.create("another-user", "another secure password")
    store = SecretStore(database)
    return database, store, admin, owner, another


def test_secret_metadata_never_contains_value_path_or_digest(vault):
    database, store, _admin, owner, _another = vault
    metadata = store.create(
        owner.actor,
        owner.id,
        "Primary Discord",
        "discord_webhook",
        "https://discord.invalid/api/webhooks/synthetic/private",
    )

    assert metadata.configured is True
    assert metadata.version == 1
    assert not hasattr(metadata, "value")
    assert not hasattr(metadata, "file_name")
    assert not hasattr(metadata, "value_sha256")
    assert store.resolve(owner.actor, metadata.id).startswith(b"https://discord.invalid/")

    with database.connect() as connection:
        row = connection.execute(
            "SELECT file_name, value_sha256 FROM secret_records WHERE id = ?",
            (metadata.id,),
        ).fetchone()
    path = store.directory / row["file_name"]
    assert store.directory.stat().st_mode & 0o777 == 0o700
    assert path.stat().st_mode & 0o777 == 0o600
    assert "synthetic/private" not in row["value_sha256"]
    assert b"synthetic/private" not in database.path.read_bytes()


def test_secret_access_is_owner_or_admin_only(vault):
    _database, store, admin, owner, another = vault
    metadata = store.create(owner.actor, owner.id, "SMTP", "smtp_password", "private")

    with pytest.raises(PermissionError):
        store.metadata(another.actor, metadata.id)
    with pytest.raises(PermissionError):
        store.resolve(another.actor, metadata.id)
    with pytest.raises(PermissionError):
        store.rotate(another.actor, metadata.id, "replacement")
    assert store.resolve(admin.actor, metadata.id) == b"private"


def test_secret_rotation_is_versioned_and_removes_previous_file(vault):
    database, store, _admin, owner, _another = vault
    metadata = store.create(owner.actor, owner.id, "Webhook", "webhook", "first")
    with database.connect() as connection:
        first_file = connection.execute(
            "SELECT file_name FROM secret_records WHERE id = ?",
            (metadata.id,),
        ).fetchone()[0]

    rotated = store.rotate(owner.actor, metadata.id, "second")
    with database.connect() as connection:
        second_file = connection.execute(
            "SELECT file_name FROM secret_records WHERE id = ?",
            (metadata.id,),
        ).fetchone()[0]

    assert rotated.version == 2
    assert second_file != first_file
    assert not (store.directory / first_file).exists()
    assert store.resolve(owner.actor, metadata.id) == b"second"


def test_secret_file_permissions_and_integrity_are_enforced(vault):
    database, store, _admin, owner, _another = vault
    metadata = store.create(owner.actor, owner.id, "Webhook", "webhook", "original")
    with database.connect() as connection:
        file_name = connection.execute(
            "SELECT file_name FROM secret_records WHERE id = ?",
            (metadata.id,),
        ).fetchone()[0]
    path = store.directory / file_name

    path.chmod(0o644)
    with pytest.raises(PermissionError, match="mode 0600"):
        store.resolve(owner.actor, metadata.id)
    path.chmod(0o600)
    path.write_bytes(b"modified")
    path.chmod(0o600)
    with pytest.raises(RuntimeError, match="integrity"):
        store.resolve(owner.actor, metadata.id)


def test_secret_names_are_unique_per_owner_but_not_globally(vault):
    _database, store, _admin, owner, another = vault
    store.create(owner.actor, owner.id, "Webhook", "webhook", "first")
    with pytest.raises(ValueError, match="already configured"):
        store.create(owner.actor, owner.id, "webhook", "webhook", "second")

    created = store.create(another.actor, another.id, "Webhook", "webhook", "other")
    assert created.owner_user_id == another.id


def test_secret_values_are_bounded(vault):
    _database, store, _admin, owner, _another = vault
    with pytest.raises(ValueError, match="must not be empty"):
        store.create(owner.actor, owner.id, "Empty", "generic", "")

    small_store = SecretStore(store.database, store.directory, maximum_bytes=4)
    with pytest.raises(ValueError, match="must not exceed"):
        small_store.create(owner.actor, owner.id, "Large", "generic", "12345")
