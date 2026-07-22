"""Persistent local-account management and login protection."""

from __future__ import annotations

import sqlite3
import time
import uuid
import base64
import binascii
import re

from dataclasses import dataclass
from typing import Callable

from api.security import hash_password, verify_password
from storage.database import Database
from storage.ownership import Actor
from storage.validation import normalized_identifier


@dataclass(frozen=True)
class User:
    id: str
    username: str
    role: str
    enabled: bool
    failed_login_count: int
    locked_until: int | None
    last_login_at: int | None
    created_at: int
    updated_at: int
    avatar_data: str | None = None

    @property
    def actor(self) -> Actor:
        return Actor(self.id, self.role)


class UserStore:
    """Manage accounts without ever returning password records."""

    def __init__(
        self,
        database: Database,
        *,
        clock: Callable[[], float] = time.time,
        password_hasher: Callable[[str], str] = hash_password,
        password_verifier: Callable[[str, str], bool] = verify_password,
        max_failed_logins: int = 5,
        lockout_seconds: int = 900,
    ):
        self.database = database
        self.clock = clock
        self.password_hasher = password_hasher
        self.password_verifier = password_verifier
        self.max_failed_logins = max(1, int(max_failed_logins))
        self.lockout_seconds = max(1, int(lockout_seconds))
        self._dummy_password_hash = self.password_hasher(
            "notifinho-dummy-password-record"
        )

    def create(self, username: str, password: str, role: str = "user") -> User:
        display, normalized = normalized_identifier(
            username,
            "username",
            minimum=3,
            maximum=64,
        )
        normalized_role = str(role or "").casefold()
        if normalized_role not in {"admin", "user"}:
            raise ValueError("role must be admin or user")
        password_record = self.password_hasher(password)
        user_id = uuid.uuid4().hex
        now = int(self.clock())
        try:
            with self.database.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO users(
                        id, username, username_normalized, password_hash, role,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        display,
                        normalized,
                        password_record,
                        normalized_role,
                        now,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise ValueError("username is already configured") from error
        return self.get(user_id)

    def bootstrap_admin(self, username: str, password: str) -> User:
        if self.count():
            raise ValueError("account bootstrap is allowed only when no users exist")
        return self.create(username, password, role="admin")

    def count(self) -> int:
        """Return the account count without exposing any credential record."""

        with self.database.connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0])

    def get(self, user_id: str) -> User:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT id, username, role, enabled, failed_login_count,
                       locked_until, last_login_at, created_at, updated_at,
                       avatar_data
                FROM users WHERE id = ?
                """,
                (str(user_id),),
            ).fetchone()
        if row is None:
            raise KeyError("user not found")
        return self._user(row)

    def get_by_username(self, username: str) -> User:
        _display, normalized = normalized_identifier(
            username,
            "username",
            minimum=3,
            maximum=64,
        )
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT id, username, role, enabled, failed_login_count,
                       locked_until, last_login_at, created_at, updated_at,
                       avatar_data
                FROM users WHERE username_normalized = ?
                """,
                (normalized,),
            ).fetchone()
        if row is None:
            raise KeyError("user not found")
        return self._user(row)

    def list(self) -> list[User]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, username, role, enabled, failed_login_count,
                       locked_until, last_login_at, created_at, updated_at,
                       avatar_data
                FROM users ORDER BY username_normalized
                """
            ).fetchall()
        return [self._user(row) for row in rows]

    def authenticate(self, username: str, password: str) -> User | None:
        try:
            _display, normalized = normalized_identifier(
                username,
                "username",
                minimum=3,
                maximum=64,
            )
        except ValueError:
            normalized = ""
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE username_normalized = ?",
                (normalized,),
            ).fetchone()
        password_record = (
            str(row["password_hash"]) if row is not None else self._dummy_password_hash
        )
        password_matches = self.password_verifier(str(password or ""), password_record)
        if row is None:
            return None

        now = int(self.clock())
        enabled = bool(row["enabled"])
        locked_until = row["locked_until"]
        locked = locked_until is not None and int(locked_until) > now
        if not enabled or locked:
            return None

        failed_count = int(row["failed_login_count"])
        if locked_until is not None and int(locked_until) <= now:
            failed_count = 0

        if not password_matches:
            failed_count += 1
            next_lock = (
                now + self.lockout_seconds
                if failed_count >= self.max_failed_logins
                else None
            )
            with self.database.transaction() as connection:
                connection.execute(
                    """
                    UPDATE users
                    SET failed_login_count = ?, locked_until = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (failed_count, next_lock, now, row["id"]),
                )
            return None

        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE users
                SET failed_login_count = 0, locked_until = NULL,
                    last_login_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, now, row["id"]),
            )
        return self.get(str(row["id"]))

    def reset_password(self, user_id: str, password: str) -> User:
        password_record = self.password_hasher(password)
        now = int(self.clock())
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE users
                SET password_hash = ?, failed_login_count = 0,
                    locked_until = NULL, updated_at = ?
                WHERE id = ?
                """,
                (password_record, now, str(user_id)),
            )
            if cursor.rowcount != 1:
                raise KeyError("user not found")
            connection.execute(
                "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                (now, str(user_id)),
            )
        return self.get(user_id)

    def set_enabled(self, user_id: str, enabled: bool) -> User:
        now = int(self.clock())
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT role, enabled FROM users WHERE id = ?",
                (str(user_id),),
            ).fetchone()
            if row is None:
                raise KeyError("user not found")
            if not enabled and row["role"] == "admin" and bool(row["enabled"]):
                remaining = int(
                    connection.execute(
                        """
                        SELECT COUNT(*) FROM users
                        WHERE role = 'admin' AND enabled = 1 AND id != ?
                        """,
                        (str(user_id),),
                    ).fetchone()[0]
                )
                if not remaining:
                    raise ValueError("the last enabled administrator cannot be disabled")
            connection.execute(
                "UPDATE users SET enabled = ?, updated_at = ? WHERE id = ?",
                (1 if enabled else 0, now, str(user_id)),
            )
            if not enabled:
                connection.execute(
                    """
                    UPDATE sessions SET revoked_at = ?
                    WHERE user_id = ? AND revoked_at IS NULL
                    """,
                    (now, str(user_id)),
                )
        return self.get(user_id)

    def set_avatar(self, user_id: str, avatar_data: str | None) -> User:
        """Store a small browser-safe raster avatar inside the protected DB."""

        normalized = None
        if avatar_data not in (None, ""):
            value = str(avatar_data)
            match = re.fullmatch(
                r"data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/]+={0,2})",
                value,
            )
            if match is None:
                raise ValueError("profile picture must be PNG, JPEG, or WebP")
            try:
                payload = base64.b64decode(match.group(2), validate=True)
            except (binascii.Error, ValueError) as error:
                raise ValueError("profile picture is invalid") from error
            if not payload or len(payload) > 256 * 1024:
                raise ValueError("profile picture must not exceed 256 KiB")
            signatures = {
                "png": payload.startswith(b"\x89PNG\r\n\x1a\n"),
                "jpeg": payload.startswith(b"\xff\xd8\xff"),
                "webp": payload.startswith(b"RIFF") and payload[8:12] == b"WEBP",
            }
            if not signatures[match.group(1)]:
                raise ValueError("profile picture content does not match its type")
            normalized = value
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "UPDATE users SET avatar_data = ?, updated_at = ? WHERE id = ?",
                (normalized, int(self.clock()), str(user_id)),
            )
            if cursor.rowcount != 1:
                raise KeyError("user not found")
        return self.get(user_id)

    @staticmethod
    def _user(row) -> User:
        return User(
            id=str(row["id"]),
            username=str(row["username"]),
            role=str(row["role"]),
            enabled=bool(row["enabled"]),
            failed_login_count=int(row["failed_login_count"]),
            locked_until=(
                int(row["locked_until"]) if row["locked_until"] is not None else None
            ),
            last_login_at=(
                int(row["last_login_at"]) if row["last_login_at"] is not None else None
            ),
            created_at=int(row["created_at"]),
            updated_at=int(row["updated_at"]),
            avatar_data=(
                str(row["avatar_data"])
                if "avatar_data" in row.keys() and row["avatar_data"]
                else None
            ),
        )
