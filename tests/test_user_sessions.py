"""Local-account, login-lockout, session, and CSRF tests."""

from __future__ import annotations

from api.security import hash_password
from storage.database import Database
from storage.sessions import SessionStore
from storage.users import UserStore

import pytest


class Clock:
    def __init__(self, value=1_800_000_000):
        self.value = value

    def __call__(self):
        return self.value


def fast_hash(password: str) -> str:
    return hash_password(password, salt=b"\x01" * 16, iterations=1_000)


@pytest.fixture
def accounts(tmp_path):
    database = Database(tmp_path / "state" / "notifinho.db")
    database.migrate()
    clock = Clock()
    users = UserStore(
        database,
        clock=clock,
        password_hasher=fast_hash,
        max_failed_logins=3,
        lockout_seconds=60,
    )
    return database, clock, users


def test_bootstrap_admin_is_one_time_and_password_is_never_returned(accounts):
    database, _clock, users = accounts
    admin = users.bootstrap_admin("Administrator", "correct horse battery staple")

    assert admin.username == "Administrator"
    assert admin.role == "admin"
    assert not hasattr(admin, "password_hash")
    assert users.authenticate("administrator", "correct horse battery staple") is not None

    with database.connect() as connection:
        record = connection.execute(
            "SELECT password_hash FROM users WHERE id = ?",
            (admin.id,),
        ).fetchone()[0]
    assert "correct horse battery staple" not in record
    assert b"correct horse battery staple" not in database.path.read_bytes()
    with pytest.raises(ValueError, match="only when no users exist"):
        users.bootstrap_admin("Another", "another correct horse battery")


def test_usernames_are_case_insensitive_and_restricted(accounts):
    _database, _clock, users = accounts
    users.create("Operator.One", "operator password value", role="user")

    with pytest.raises(ValueError, match="already configured"):
        users.create("operator.one", "different password value", role="user")
    with pytest.raises(ValueError, match="must start"):
        users.create("invalid name", "different password value", role="user")
    with pytest.raises(ValueError, match="role"):
        users.create("valid-user", "different password value", role="owner")


def test_failed_logins_persist_lockout_and_expire(accounts):
    _database, clock, users = accounts
    user = users.create("operator", "correct horse battery staple")

    assert users.authenticate("operator", "wrong password") is None
    assert users.authenticate("operator", "wrong password") is None
    assert users.authenticate("operator", "wrong password") is None
    locked = users.get(user.id)
    assert locked.failed_login_count == 3
    assert locked.locked_until == clock.value + 60
    assert users.authenticate("operator", "correct horse battery staple") is None

    clock.value += 61
    authenticated = users.authenticate("operator", "correct horse battery staple")
    assert authenticated is not None
    assert authenticated.failed_login_count == 0
    assert authenticated.locked_until is None
    assert authenticated.last_login_at == clock.value


def test_missing_user_runs_password_verifier(accounts):
    _database, _clock, users = accounts
    calls = []
    users.password_verifier = lambda password, record: calls.append((password, record)) or False

    assert users.authenticate("missing-user", "synthetic missing password") is None
    assert len(calls) == 1
    assert calls[0][1].startswith("pbkdf2_sha256$")


def test_last_enabled_admin_cannot_be_disabled(accounts):
    _database, _clock, users = accounts
    first = users.bootstrap_admin("first-admin", "correct horse battery staple")
    with pytest.raises(ValueError, match="last enabled administrator"):
        users.set_enabled(first.id, False)

    users.create("second-admin", "another correct horse battery", role="admin")
    disabled = users.set_enabled(first.id, False)
    assert disabled.enabled is False
    assert users.authenticate("first-admin", "correct horse battery staple") is None


def test_session_tokens_and_csrf_values_are_hashed(accounts):
    database, clock, users = accounts
    user = users.bootstrap_admin("administrator", "correct horse battery staple")
    sessions = SessionStore(
        database,
        clock=clock,
        absolute_ttl_seconds=600,
        idle_ttl_seconds=120,
    )
    credentials = sessions.create(user.id)

    with database.connect() as connection:
        row = connection.execute(
            "SELECT token_hash, csrf_hash FROM sessions WHERE id = ?",
            (credentials.session_id,),
        ).fetchone()
    assert credentials.session_token not in tuple(row)
    assert credentials.csrf_token not in tuple(row)
    database_bytes = database.path.read_bytes()
    assert credentials.session_token.encode() not in database_bytes
    assert credentials.csrf_token.encode() not in database_bytes
    assert sessions.authenticate(credentials.session_token, touch=False) is not None
    assert sessions.authenticate(
        credentials.session_token,
        csrf_token="wrong",
        require_csrf=True,
    ) is None
    principal = sessions.authenticate(
        credentials.session_token,
        csrf_token=credentials.csrf_token,
        require_csrf=True,
    )
    assert principal is not None
    assert principal.user_id == user.id
    assert principal.actor.is_admin is True


def test_session_idle_expiry_revocation_and_purge(accounts):
    database, clock, users = accounts
    user = users.bootstrap_admin("administrator", "correct horse battery staple")
    sessions = SessionStore(
        database,
        clock=clock,
        absolute_ttl_seconds=600,
        idle_ttl_seconds=60,
    )
    first = sessions.create(user.id)
    clock.value += 61
    assert sessions.authenticate(first.session_token) is None
    assert sessions.purge_expired() == 1

    second = sessions.create(user.id)
    assert sessions.revoke(second.session_id) is True
    assert sessions.revoke(second.session_id) is False
    assert sessions.authenticate(second.session_token) is None


def test_password_reset_and_account_disable_revoke_sessions(accounts):
    database, clock, users = accounts
    admin = users.bootstrap_admin("first-admin", "correct horse battery staple")
    other = users.create("second-admin", "another correct horse battery", role="admin")
    sessions = SessionStore(database, clock=clock)

    initial = sessions.create(admin.id)
    users.reset_password(admin.id, "replacement secure password")
    assert sessions.authenticate(initial.session_token) is None
    assert users.authenticate("first-admin", "replacement secure password") is not None

    replacement = sessions.create(admin.id)
    users.set_enabled(admin.id, False)
    assert sessions.authenticate(replacement.session_token) is None
    assert other.enabled is True


def test_session_cookie_defaults_are_browser_safe(accounts):
    database, clock, users = accounts
    user = users.bootstrap_admin("administrator", "correct horse battery staple")
    credentials = SessionStore(database, clock=clock).create(user.id)
    cookie = credentials.cookie()

    assert cookie.startswith("__Host-notifinho_session=")
    assert "; HttpOnly" in cookie
    assert "; Secure" in cookie
    assert "; SameSite=Strict" in cookie
    assert "; Path=/" in cookie
