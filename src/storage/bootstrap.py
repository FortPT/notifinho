"""Single-use, log-delivered first-run administrator bootstrap."""

from __future__ import annotations

import hmac
import secrets
import threading
import time
import uuid

from dataclasses import dataclass
from typing import Callable

from api.security import hash_token
from storage.database import Database
from storage.users import User, UserStore


@dataclass(frozen=True)
class BootstrapCredential:
    """Plaintext credential returned only at generation time."""

    token: str
    expires_at: int


@dataclass(frozen=True)
class BootstrapStatus:
    required: bool
    expires_at: int | None


class BootstrapStore:
    """Rotate and consume one active setup token while no accounts exist."""

    def __init__(
        self,
        database: Database,
        *,
        users: UserStore | None = None,
        clock: Callable[[], float] = time.time,
        token_factory: Callable[[int], str] = secrets.token_urlsafe,
        ttl_seconds: int = 1800,
    ):
        self.database = database
        self.users = users or UserStore(database)
        self.clock = clock
        self.token_factory = token_factory
        self.ttl_seconds = max(300, min(int(ttl_seconds), 86_400))
        self._lock = threading.Lock()

    def rotate_for_startup(self) -> BootstrapCredential | None:
        """Create a fresh token on each start until the first user exists."""

        with self._lock:
            if self.users.count():
                self._consume_all()
                return None
            now = int(self.clock())
            token = self.token_factory(32)
            expires_at = now + self.ttl_seconds
            with self.database.transaction() as connection:
                connection.execute(
                    "UPDATE bootstrap_tokens SET consumed_at = ? WHERE consumed_at IS NULL",
                    (now,),
                )
                connection.execute(
                    """
                    INSERT INTO bootstrap_tokens(
                        id, token_hash, created_at, expires_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (uuid.uuid4().hex, hash_token(token), now, expires_at),
                )
            return BootstrapCredential(token=token, expires_at=expires_at)

    def status(self) -> BootstrapStatus:
        if self.users.count():
            return BootstrapStatus(required=False, expires_at=None)
        now = int(self.clock())
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT expires_at FROM bootstrap_tokens
                WHERE consumed_at IS NULL
                ORDER BY created_at DESC LIMIT 1
                """
            ).fetchone()
        expires_at = int(row["expires_at"]) if row is not None else None
        return BootstrapStatus(
            required=True,
            expires_at=expires_at if expires_at and expires_at > now else None,
        )

    def consume(self, token: str, username: str, password: str) -> User:
        """Create the only first administrator and invalidate the setup token."""

        candidate_hash = hash_token(str(token or ""))
        with self._lock:
            if self.users.count():
                raise ValueError("platform setup is already complete")
            now = int(self.clock())
            with self.database.connect() as connection:
                row = connection.execute(
                    """
                    SELECT id, token_hash, expires_at FROM bootstrap_tokens
                    WHERE consumed_at IS NULL
                    ORDER BY created_at DESC LIMIT 1
                    """
                ).fetchone()
            valid = (
                row is not None
                and int(row["expires_at"]) > now
                and hmac.compare_digest(candidate_hash, str(row["token_hash"]))
            )
            if not valid:
                raise PermissionError("bootstrap token is invalid or expired")
            user = self.users.bootstrap_admin(username, password)
            with self.database.transaction() as connection:
                connection.execute(
                    "UPDATE bootstrap_tokens SET consumed_at = ? WHERE id = ?",
                    (now, str(row["id"])),
                )
            return user

    def _consume_all(self) -> None:
        now = int(self.clock())
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE bootstrap_tokens SET consumed_at = ? WHERE consumed_at IS NULL",
                (now,),
            )
