"""User-owned, source-scoped API-token lifecycle and authentication."""

from __future__ import annotations

import json
import secrets
import sqlite3
import time
import uuid

from dataclasses import dataclass
from typing import Callable

from api.security import hash_token
from storage.audit_events import AuditEventStore
from storage.database import Database
from storage.ownership import Actor, OwnershipPolicy
from storage.validation import normalized_identifier, normalized_name


@dataclass(frozen=True)
class APIToken:
    id: str
    owner_user_id: str
    name: str
    role: str
    source_scopes: tuple[str, ...]
    rate_limit_per_minute: int
    version: int
    created_at: int
    updated_at: int
    expires_at: int | None
    last_used_at: int | None
    revoked_at: int | None
    enabled: bool = True

@dataclass(frozen=True)
class TokenCredentials:
    token: APIToken
    value: str


@dataclass(frozen=True)
class TokenPrincipal:
    token_id: str
    token_name: str
    owner_user_id: str
    owner_role: str
    token_role: str
    source_scopes: frozenset[str]
    rate_limit_per_minute: int

    @property
    def name(self) -> str:
        """Compatibility with the existing in-memory API rate limiter."""

        return f"platform-token:{self.token_id}"

    @property
    def actor(self) -> Actor:
        return Actor(self.owner_user_id, self.owner_role)

    def allows(self, source: str) -> bool:
        normalized = str(source or "").casefold()
        return "*" in self.source_scopes or normalized in self.source_scopes


class APITokenStore:
    def __init__(
        self,
        database: Database,
        *,
        audit: AuditEventStore | None = None,
        clock: Callable[[], float] = time.time,
    ):
        self.database = database
        self.audit = audit
        self.clock = clock

    def create(
        self,
        actor: Actor,
        owner_user_id: str,
        name: str,
        *,
        source_scopes,
        role: str = "application",
        rate_limit_per_minute: int = 60,
        expires_at: int | None = None,
    ) -> TokenCredentials:
        OwnershipPolicy.require_write(actor, str(owner_user_id))
        display, normalized_name_value = normalized_name(name, "token name")
        normalized_role = str(role or "").casefold()
        if normalized_role not in {"admin", "application"}:
            raise ValueError("token role must be admin or application")
        scopes = self._scopes(source_scopes)
        rate_limit = int(rate_limit_per_minute)
        if not 1 <= rate_limit <= 10_000:
            raise ValueError("rate limit must be between 1 and 10000")
        now = int(self.clock())
        if expires_at is not None and int(expires_at) <= now:
            raise ValueError("token expiry must be in the future")

        token_id = uuid.uuid4().hex
        value = self._new_value()
        try:
            with self.database.transaction() as connection:
                owner = connection.execute(
                    "SELECT role, enabled FROM users WHERE id = ?",
                    (str(owner_user_id),),
                ).fetchone()
                if owner is None:
                    raise KeyError("token owner not found")
                if not bool(owner["enabled"]):
                    raise PermissionError("disabled users cannot own new tokens")
                if normalized_role == "admin" and (
                    not actor.is_admin or str(owner["role"]) != "admin"
                ):
                    raise PermissionError("administrator tokens require an administrator")
                if "*" in scopes and not actor.is_admin:
                    raise PermissionError("wildcard source scope requires an administrator")
                connection.execute(
                    """
                    INSERT INTO api_tokens(
                        id, owner_user_id, name, name_normalized, token_hash,
                        role, source_scopes, rate_limit_per_minute, created_at,
                        expires_at, version, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                    """,
                    (
                        token_id,
                        str(owner_user_id),
                        display,
                        normalized_name_value,
                        hash_token(value),
                        normalized_role,
                        json.dumps(scopes, separators=(",", ":")),
                        rate_limit,
                        now,
                        int(expires_at) if expires_at is not None else None,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise ValueError("token name is already configured for this owner") from error
        token = self.get(actor, token_id)
        self._audit(actor, "token.create", token_id, "success", {"role": token.role})
        return TokenCredentials(token, value)

    def authenticate(self, supplied: str, source: str = "") -> TokenPrincipal | None:
        candidate = str(supplied or "")
        if not candidate:
            return None
        now = int(self.clock())
        with self.database.transaction() as connection:
            row = connection.execute(
                """
                SELECT api_tokens.*, users.role AS owner_role,
                       users.enabled AS owner_enabled
                FROM api_tokens
                JOIN users ON users.id = api_tokens.owner_user_id
                WHERE api_tokens.token_hash = ?
                """,
                (hash_token(candidate),),
            ).fetchone()
            if row is None or not bool(row["owner_enabled"]):
                return None
            if "enabled" in row.keys() and not bool(row["enabled"]):
                return None
            if row["revoked_at"] is not None:
                return None
            if row["expires_at"] is not None and int(row["expires_at"]) <= now:
                return None
            scopes = frozenset(json.loads(str(row["source_scopes"])))
            principal = TokenPrincipal(
                token_id=str(row["id"]),
                token_name=str(row["name"]),
                owner_user_id=str(row["owner_user_id"]),
                owner_role=str(row["owner_role"]),
                token_role=str(row["role"]),
                source_scopes=scopes,
                rate_limit_per_minute=int(row["rate_limit_per_minute"]),
            )
            if source and not principal.allows(source):
                return None
            connection.execute(
                "UPDATE api_tokens SET last_used_at = ? WHERE id = ?",
                (now, principal.token_id),
            )
        return principal

    def get(self, actor: Actor, token_id: str) -> APIToken:
        row = self._record(token_id)
        OwnershipPolicy.require_read(actor, str(row["owner_user_id"]))
        return self._token(row)

    def list_for_owner(self, actor: Actor, owner_user_id: str) -> list[APIToken]:
        OwnershipPolicy.require_read(actor, str(owner_user_id))
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM api_tokens
                WHERE owner_user_id = ? ORDER BY name_normalized
                """,
                (str(owner_user_id),),
            ).fetchall()
        return [self._token(row) for row in rows]

    def rotate(self, actor: Actor, token_id: str) -> TokenCredentials:
        row = self._record(token_id)
        OwnershipPolicy.require_write(actor, str(row["owner_user_id"]))
        if row["revoked_at"] is not None:
            raise ValueError("revoked tokens cannot be rotated")
        value = self._new_value()
        now = int(self.clock())
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE api_tokens
                SET token_hash = ?, version = version + 1, updated_at = ?,
                    last_used_at = NULL
                WHERE id = ?
                """,
                (hash_token(value), now, str(token_id)),
            )
        token = self.get(actor, token_id)
        self._audit(actor, "token.rotate", token_id, "success", {"version": token.version})
        return TokenCredentials(token, value)

    def revoke(self, actor: Actor, token_id: str) -> APIToken:
        row = self._record(token_id)
        OwnershipPolicy.require_write(actor, str(row["owner_user_id"]))
        now = int(self.clock())
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE api_tokens
                SET revoked_at = COALESCE(revoked_at, ?), updated_at = ?
                WHERE id = ?
                """,
                (now, now, str(token_id)),
            )
        self._audit(actor, "token.revoke", token_id, "success")
        return self.get(actor, token_id)

    def set_enabled(self, actor: Actor, token_id: str, enabled: bool) -> APIToken:
        row = self._record(token_id)
        OwnershipPolicy.require_write(actor, str(row["owner_user_id"]))
        if row["revoked_at"] is not None and enabled:
            raise ValueError("revoked tokens cannot be enabled")
        now = int(self.clock())
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE api_tokens SET enabled = ?, updated_at = ? WHERE id = ?",
                (1 if enabled else 0, now, str(token_id)),
            )
        self._audit(
            actor,
            "token.enable" if enabled else "token.disable",
            token_id,
            "success",
        )
        return self.get(actor, token_id)

    def delete(self, actor: Actor, token_id: str) -> None:
        row = self._record(token_id)
        OwnershipPolicy.require_write(actor, str(row["owner_user_id"]))
        with self.database.transaction() as connection:
            connection.execute("DELETE FROM api_tokens WHERE id = ?", (str(token_id),))
        self._audit(actor, "token.delete", token_id, "success")

    def _record(self, token_id: str):
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM api_tokens WHERE id = ?",
                (str(token_id),),
            ).fetchone()
        if row is None:
            raise KeyError("token not found")
        return row

    @staticmethod
    def _token(row) -> APIToken:
        updated_at = row["updated_at"] if "updated_at" in row.keys() else None
        return APIToken(
            id=str(row["id"]),
            owner_user_id=str(row["owner_user_id"]),
            name=str(row["name"]),
            role=str(row["role"]),
            source_scopes=tuple(json.loads(str(row["source_scopes"]))),
            rate_limit_per_minute=int(row["rate_limit_per_minute"]),
            version=int(row["version"]),
            created_at=int(row["created_at"]),
            updated_at=int(updated_at or row["created_at"]),
            expires_at=(
                int(row["expires_at"]) if row["expires_at"] is not None else None
            ),
            last_used_at=(
                int(row["last_used_at"])
                if row["last_used_at"] is not None
                else None
            ),
            revoked_at=(
                int(row["revoked_at"]) if row["revoked_at"] is not None else None
            ),
            enabled=(
                bool(row["enabled"])
                if "enabled" in row.keys()
                else True
            ),
        )

    @staticmethod
    def _scopes(values) -> list[str]:
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, (list, tuple, set)) or not values:
            raise ValueError("source scopes must be a non-empty list")
        scopes = []
        for value in values:
            _display, normalized = normalized_identifier(
                value,
                "source scope",
                maximum=64,
            ) if value != "*" else ("*", "*")
            if normalized not in scopes:
                scopes.append(normalized)
        if len(scopes) > 64:
            raise ValueError("source scopes must not contain more than 64 entries")
        return scopes

    @staticmethod
    def _new_value() -> str:
        return "ntf_" + secrets.token_urlsafe(32)

    def _audit(self, actor, action, resource_id, outcome, details=None):
        if self.audit is not None:
            self.audit.write(
                actor,
                action,
                "api_token",
                resource_id,
                outcome,
                details,
            )
