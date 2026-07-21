"""Hashed local browser-session and CSRF credential storage."""

from __future__ import annotations

import hmac
import secrets
import time
import uuid

from dataclasses import dataclass
from typing import Callable

from api.security import hash_token
from storage.database import Database
from storage.ownership import Actor


@dataclass(frozen=True)
class SessionCredentials:
    """One-time session credentials returned only when a session is created."""

    session_id: str
    session_token: str
    csrf_token: str
    expires_at: int

    def cookie(self, *, secure: bool = True) -> str:
        cookie_name = "__Host-notifinho_session" if secure else "notifinho_session"
        attributes = [
            f"{cookie_name}={self.session_token}",
            "Path=/",
            "HttpOnly",
            "SameSite=Strict",
            f"Max-Age={max(0, self.expires_at - int(time.time()))}",
        ]
        if secure:
            attributes.append("Secure")
        return "; ".join(attributes)


@dataclass(frozen=True)
class SessionPrincipal:
    session_id: str
    user_id: str
    username: str
    role: str
    expires_at: int

    @property
    def actor(self) -> Actor:
        return Actor(self.user_id, self.role)


class SessionStore:
    def __init__(
        self,
        database: Database,
        *,
        clock: Callable[[], float] = time.time,
        absolute_ttl_seconds: int = 12 * 60 * 60,
        idle_ttl_seconds: int = 30 * 60,
    ):
        self.database = database
        self.clock = clock
        self.absolute_ttl_seconds = max(60, int(absolute_ttl_seconds))
        self.idle_ttl_seconds = max(60, int(idle_ttl_seconds))

    def create(self, user_id: str) -> SessionCredentials:
        now = int(self.clock())
        session_id = uuid.uuid4().hex
        session_token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        expires_at = now + self.absolute_ttl_seconds
        idle_expires_at = min(expires_at, now + self.idle_ttl_seconds)
        with self.database.transaction() as connection:
            user = connection.execute(
                "SELECT enabled FROM users WHERE id = ?",
                (str(user_id),),
            ).fetchone()
            if user is None:
                raise KeyError("user not found")
            if not bool(user["enabled"]):
                raise PermissionError("disabled users cannot create sessions")
            connection.execute(
                """
                INSERT INTO sessions(
                    id, user_id, token_hash, csrf_hash, created_at,
                    last_seen_at, expires_at, idle_expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    str(user_id),
                    hash_token(session_token),
                    hash_token(csrf_token),
                    now,
                    now,
                    expires_at,
                    idle_expires_at,
                ),
            )
        return SessionCredentials(
            session_id=session_id,
            session_token=session_token,
            csrf_token=csrf_token,
            expires_at=expires_at,
        )

    def authenticate(
        self,
        session_token: str,
        *,
        csrf_token: str = "",
        require_csrf: bool = False,
        touch: bool = True,
    ) -> SessionPrincipal | None:
        candidate_hash = hash_token(str(session_token or ""))
        if not session_token:
            return None
        now = int(self.clock())
        with self.database.transaction() as connection:
            row = connection.execute(
                """
                SELECT sessions.id, sessions.csrf_hash, sessions.expires_at,
                       sessions.idle_expires_at, sessions.revoked_at,
                       users.id AS user_id, users.username, users.role,
                       users.enabled
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token_hash = ?
                """,
                (candidate_hash,),
            ).fetchone()
            if row is None:
                return None
            if (
                row["revoked_at"] is not None
                or not bool(row["enabled"])
                or now >= int(row["expires_at"])
                or now >= int(row["idle_expires_at"])
            ):
                return None
            if require_csrf:
                supplied_hash = hash_token(str(csrf_token or ""))
                if not csrf_token or not hmac.compare_digest(
                    supplied_hash,
                    str(row["csrf_hash"]),
                ):
                    return None
            if touch:
                idle_expires_at = min(
                    int(row["expires_at"]),
                    now + self.idle_ttl_seconds,
                )
                connection.execute(
                    """
                    UPDATE sessions
                    SET last_seen_at = ?, idle_expires_at = ?
                    WHERE id = ?
                    """,
                    (now, idle_expires_at, row["id"]),
                )
            return SessionPrincipal(
                session_id=str(row["id"]),
                user_id=str(row["user_id"]),
                username=str(row["username"]),
                role=str(row["role"]),
                expires_at=int(row["expires_at"]),
            )

    def revoke(self, session_id: str) -> bool:
        now = int(self.clock())
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE sessions SET revoked_at = ?
                WHERE id = ? AND revoked_at IS NULL
                """,
                (now, str(session_id)),
            )
        return cursor.rowcount == 1

    def revoke_user(self, user_id: str) -> int:
        now = int(self.clock())
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE sessions SET revoked_at = ?
                WHERE user_id = ? AND revoked_at IS NULL
                """,
                (now, str(user_id)),
            )
        return int(cursor.rowcount)

    def purge_expired(self) -> int:
        now = int(self.clock())
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                DELETE FROM sessions
                WHERE revoked_at IS NOT NULL
                   OR expires_at <= ?
                   OR idle_expires_at <= ?
                """,
                (now, now),
            )
        return int(cursor.rowcount)
