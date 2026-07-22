"""Owner-scoped atomic secret files with non-revealing metadata."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import sqlite3
import stat
import time
import uuid

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from storage.database import Database
from storage.ownership import Actor, OwnershipPolicy
from storage.validation import normalized_identifier, normalized_name


_SECRET_FILE = re.compile(r"^[0-9a-f]{32}\.v[1-9][0-9]*$")


@dataclass(frozen=True)
class SecretMetadata:
    id: str
    owner_user_id: str
    name: str
    kind: str
    version: int
    configured: bool
    created_at: int
    updated_at: int


class SecretStore:
    """Keep secret values outside SQLite and outside API-facing metadata."""

    def __init__(
        self,
        database: Database,
        directory: str | Path | None = None,
        *,
        clock: Callable[[], float] = time.time,
        maximum_bytes: int = 64 * 1024,
    ):
        self.database = database
        self.directory = Path(directory or database.path.parent / "secrets").absolute()
        self.clock = clock
        self.maximum_bytes = max(1, int(maximum_bytes))
        self._prepare_directory()

    def create(
        self,
        actor: Actor,
        owner_user_id: str,
        name: str,
        kind: str,
        value: str | bytes,
    ) -> SecretMetadata:
        with self.database.maintenance():
            return self._create(actor, owner_user_id, name, kind, value)

    def _create(
        self,
        actor: Actor,
        owner_user_id: str,
        name: str,
        kind: str,
        value: str | bytes,
    ) -> SecretMetadata:
        OwnershipPolicy.require_write(actor, str(owner_user_id))
        display, normalized = normalized_name(name, "secret name", maximum=128)
        _kind_display, normalized_kind = normalized_identifier(
            kind,
            "secret kind",
            maximum=64,
        )
        payload = self._payload(value)
        secret_id = uuid.uuid4().hex
        version = 1
        file_name = self._file_name(secret_id, version)
        digest = hashlib.sha256(payload).hexdigest()
        now = int(self.clock())
        self._write_new(file_name, payload)
        try:
            with self.database.transaction() as connection:
                owner = connection.execute(
                    "SELECT id FROM users WHERE id = ?",
                    (str(owner_user_id),),
                ).fetchone()
                if owner is None:
                    raise KeyError("secret owner not found")
                connection.execute(
                    """
                    INSERT INTO secret_records(
                        id, owner_user_id, name, name_normalized, kind,
                        file_name, value_sha256, version, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        secret_id,
                        str(owner_user_id),
                        display,
                        normalized,
                        normalized_kind,
                        file_name,
                        digest,
                        version,
                        now,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as error:
            self._remove(file_name)
            raise ValueError("secret name is already configured for this owner") from error
        except Exception:
            self._remove(file_name)
            raise
        return self.metadata(actor, secret_id)

    def metadata(self, actor: Actor, secret_id: str) -> SecretMetadata:
        row = self._record(secret_id)
        OwnershipPolicy.require_read(actor, str(row["owner_user_id"]), shared=False)
        return self._metadata(row)

    def list_for_owner(self, actor: Actor, owner_user_id: str) -> list[SecretMetadata]:
        OwnershipPolicy.require_read(actor, str(owner_user_id), shared=False)
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM secret_records
                WHERE owner_user_id = ? ORDER BY name_normalized
                """,
                (str(owner_user_id),),
            ).fetchall()
        return [self._metadata(row) for row in rows]

    def resolve(self, actor: Actor, secret_id: str) -> bytes:
        """Resolve a value for an authorized internal delivery operation."""

        with self.database.maintenance():
            return self._resolve(actor, secret_id)

    def _resolve(self, actor: Actor, secret_id: str) -> bytes:

        row = self._record(secret_id)
        OwnershipPolicy.require_read(actor, str(row["owner_user_id"]), shared=False)
        payload = self._read(str(row["file_name"]))
        digest = hashlib.sha256(payload).hexdigest()
        if not hmac.compare_digest(digest, str(row["value_sha256"])):
            raise RuntimeError("secret file integrity check failed")
        return payload

    def rotate(self, actor: Actor, secret_id: str, value: str | bytes) -> SecretMetadata:
        with self.database.maintenance():
            return self._rotate(actor, secret_id, value)

    def _rotate(
        self,
        actor: Actor,
        secret_id: str,
        value: str | bytes,
    ) -> SecretMetadata:
        row = self._record(secret_id)
        OwnershipPolicy.require_write(actor, str(row["owner_user_id"]))
        payload = self._payload(value)
        next_version = int(row["version"]) + 1
        next_file = self._file_name(str(row["id"]), next_version)
        previous_file = str(row["file_name"])
        digest = hashlib.sha256(payload).hexdigest()
        now = int(self.clock())
        self._write_new(next_file, payload)
        try:
            with self.database.transaction() as connection:
                cursor = connection.execute(
                    """
                    UPDATE secret_records
                    SET file_name = ?, value_sha256 = ?, version = ?, updated_at = ?
                    WHERE id = ? AND version = ?
                    """,
                    (
                        next_file,
                        digest,
                        next_version,
                        now,
                        str(secret_id),
                        int(row["version"]),
                    ),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("secret was changed by another operation")
        except Exception:
            self._remove(next_file)
            raise
        self._remove(previous_file)
        return self.metadata(actor, secret_id)

    def delete(self, actor: Actor, secret_id: str) -> None:
        """Delete an unreferenced secret record and its value file."""

        with self.database.maintenance():
            self._delete(actor, secret_id)

    def _delete(self, actor: Actor, secret_id: str) -> None:

        row = self._record(secret_id)
        OwnershipPolicy.require_write(actor, str(row["owner_user_id"]))
        try:
            with self.database.transaction() as connection:
                connection.execute(
                    "DELETE FROM secret_records WHERE id = ?",
                    (str(secret_id),),
                )
        except sqlite3.IntegrityError as error:
            raise ValueError("secret is referenced by a destination") from error
        self._remove(str(row["file_name"]))

    def _record(self, secret_id: str):
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM secret_records WHERE id = ?",
                (str(secret_id),),
            ).fetchone()
        if row is None:
            raise KeyError("secret not found")
        return row

    @staticmethod
    def _metadata(row) -> SecretMetadata:
        return SecretMetadata(
            id=str(row["id"]),
            owner_user_id=str(row["owner_user_id"]),
            name=str(row["name"]),
            kind=str(row["kind"]),
            version=int(row["version"]),
            configured=True,
            created_at=int(row["created_at"]),
            updated_at=int(row["updated_at"]),
        )

    def _payload(self, value: str | bytes) -> bytes:
        payload = value if isinstance(value, bytes) else str(value or "").encode("utf-8")
        if not payload:
            raise ValueError("secret value must not be empty")
        if len(payload) > self.maximum_bytes:
            raise ValueError(f"secret value must not exceed {self.maximum_bytes} bytes")
        return payload

    def _prepare_directory(self) -> None:
        if self.directory.is_symlink():
            raise ValueError("secret directory must not be a symbolic link")
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.directory, 0o700)

    @staticmethod
    def _file_name(secret_id: str, version: int) -> str:
        if not re.fullmatch(r"[0-9a-f]{32}", str(secret_id)):
            raise ValueError("invalid secret identifier")
        return f"{secret_id}.v{int(version)}"

    def _path(self, file_name: str) -> Path:
        if not _SECRET_FILE.fullmatch(str(file_name)):
            raise RuntimeError("invalid stored secret file name")
        return self.directory / file_name

    def _write_new(self, file_name: str, payload: bytes) -> None:
        self._prepare_directory()
        path = self._path(file_name)
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(path, 0o600)
        except Exception:
            path.unlink(missing_ok=True)
            raise

    def _read(self, file_name: str) -> bytes:
        path = self._path(file_name)
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as stream:
            details = os.fstat(stream.fileno())
            if not stat.S_ISREG(details.st_mode) or details.st_mode & 0o077:
                raise PermissionError("secret file must be regular and mode 0600")
            payload = stream.read(self.maximum_bytes + 1)
        if len(payload) > self.maximum_bytes:
            raise ValueError("secret file exceeds the configured size limit")
        return payload

    def _remove(self, file_name: str) -> None:
        self._path(file_name).unlink(missing_ok=True)
