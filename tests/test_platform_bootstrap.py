"""Secure first-run bootstrap token and administrator-creation tests."""

from __future__ import annotations

import pytest

from api.security import hash_password, hash_token
from storage.bootstrap import BootstrapStore
from storage.database import Database
from storage.users import UserStore


class Clock:
    def __init__(self, value=1_900_000_000):
        self.value = value

    def __call__(self):
        return self.value


def fast_hash(password: str) -> str:
    return hash_password(password, salt=b"\x09" * 16, iterations=1_000)


def stores(tmp_path):
    database = Database(tmp_path / "state" / "notifinho.db")
    database.migrate()
    clock = Clock()
    users = UserStore(database, clock=clock, password_hasher=fast_hash)
    sequence = iter(("first-setup-token", "rotated-setup-token"))
    bootstrap = BootstrapStore(
        database,
        users=users,
        clock=clock,
        token_factory=lambda _size: next(sequence),
        ttl_seconds=300,
    )
    return database, clock, users, bootstrap


def test_startup_token_is_digest_only_rotated_and_single_use(tmp_path):
    database, _clock, users, bootstrap = stores(tmp_path)

    first = bootstrap.rotate_for_startup()
    second = bootstrap.rotate_for_startup()

    assert first.token == "first-setup-token"
    assert second.token == "rotated-setup-token"
    assert first.token.encode() not in database.path.read_bytes()
    assert second.token.encode() not in database.path.read_bytes()
    with database.connect() as connection:
        rows = connection.execute(
            "SELECT token_hash, consumed_at FROM bootstrap_tokens ORDER BY created_at, id"
        ).fetchall()
    assert {row["token_hash"] for row in rows} == {
        hash_token(first.token),
        hash_token(second.token),
    }
    assert sum(row["consumed_at"] is None for row in rows) == 1

    with pytest.raises(PermissionError):
        bootstrap.consume(
            first.token,
            "administrator",
            "correct horse battery staple",
        )
    admin = bootstrap.consume(
        second.token,
        "administrator",
        "correct horse battery staple",
    )
    assert admin.role == "admin"
    assert users.authenticate(
        "administrator",
        "correct horse battery staple",
    ) is not None
    assert bootstrap.status().required is False
    assert bootstrap.rotate_for_startup() is None

    with pytest.raises(ValueError, match="already complete"):
        bootstrap.consume(
            second.token,
            "another-admin",
            "another secure password",
        )


def test_expired_token_never_creates_an_account(tmp_path):
    _database, clock, users, bootstrap = stores(tmp_path)
    credential = bootstrap.rotate_for_startup()
    clock.value = credential.expires_at

    assert bootstrap.status().required is True
    assert bootstrap.status().expires_at is None
    with pytest.raises(PermissionError, match="invalid or expired"):
        bootstrap.consume(
            credential.token,
            "administrator",
            "correct horse battery staple",
        )
    assert users.count() == 0
