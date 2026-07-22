"""Server-side, integrity-checked backups for platform database and secrets."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import shutil
import sqlite3
import stat
import threading
import time
import uuid

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from storage.audit_events import AuditEventStore
from storage.database import Database
from storage.migrations import LATEST_SCHEMA_VERSION
from storage.ownership import Actor


BACKUP_SCHEMA = "notifinho.state-backup.v1"
_BACKUP_ID = re.compile(r"^state-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$")
_SECRET_FILE = re.compile(r"^[0-9a-f]{32}\.v[1-9][0-9]*$")
_MAXIMUM_SECRET_FILES = 5000
_MAXIMUM_SECRET_BYTES = 64 * 1024


@dataclass(frozen=True)
class StateBackup:
    id: str
    created_at: int
    schema_version: int
    secret_files: int
    size_bytes: int

    def public(self) -> dict:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "schema_version": self.schema_version,
            "secret_files": self.secret_files,
            "size_bytes": self.size_bytes,
        }


class StateBackupStore:
    """Create and restore private snapshots without returning secret bytes."""

    def __init__(
        self,
        database: Database,
        *,
        secret_directory: str | Path | None = None,
        backup_directory: str | Path | None = None,
        audit: AuditEventStore | None = None,
        clock=time.time,
        retention: int = 20,
    ):
        self.database = database
        self.secret_directory = Path(
            secret_directory or database.path.parent / "secrets"
        ).absolute()
        self.backup_directory = Path(
            backup_directory or database.path.parent / "backups"
        ).absolute()
        self.audit = audit
        self.clock = clock
        self.retention = max(1, min(100, int(retention)))
        self._lock = threading.RLock()
        self._prepare_directory(self.backup_directory)

    def list(self, actor: Actor) -> list[StateBackup]:
        self._require_admin(actor)
        backups = []
        with self._lock:
            for path in sorted(self.backup_directory.iterdir(), reverse=True):
                if path.is_dir() and _BACKUP_ID.fullmatch(path.name):
                    try:
                        backups.append(self._validate(path))
                    except (OSError, RuntimeError, TypeError, ValueError):
                        continue
        return backups

    def create(
        self,
        actor: Actor,
        *,
        protected: set[str] | None = None,
    ) -> StateBackup:
        self._require_admin(actor)
        with self._lock, self.database.maintenance():
            stamp = datetime.fromtimestamp(
                self.clock(),
                timezone.utc,
            ).strftime("%Y%m%dT%H%M%SZ")
            backup_id = f"state-{stamp}-{uuid.uuid4().hex[:8]}"
            final = self.backup_directory / backup_id
            temporary = self.backup_directory / f".create-{uuid.uuid4().hex}"
            temporary.mkdir(mode=0o700)
            os.chmod(temporary, 0o700)
            try:
                database_target = temporary / "notifinho.db"
                self._snapshot_database(database_target)
                secret_target = temporary / "secrets"
                secret_target.mkdir(mode=0o700)
                files = {"notifinho.db": self._digest(database_target)}
                secret_count = 0
                if self.secret_directory.exists():
                    if self.secret_directory.is_symlink():
                        raise ValueError("secret directory must not be a symbolic link")
                    directory_mode = self.secret_directory.stat().st_mode
                    if not stat.S_ISDIR(directory_mode) or directory_mode & 0o077:
                        raise PermissionError("secret directory must be mode 0700")
                    for source in sorted(self.secret_directory.iterdir()):
                        if (
                            source.is_symlink()
                            or not source.is_file()
                            or not _SECRET_FILE.fullmatch(source.name)
                        ):
                            raise ValueError("secret directory contains an invalid file")
                        secret_count += 1
                        if secret_count > _MAXIMUM_SECRET_FILES:
                            raise ValueError("secret file count exceeds backup limit")
                        destination = secret_target / source.name
                        self._copy_secret(source, destination)
                        files[f"secrets/{source.name}"] = self._digest(destination)
                manifest = {
                    "schema": BACKUP_SCHEMA,
                    "id": backup_id,
                    "created_at": int(self.clock()),
                    "database_schema": self.database.schema_version,
                    "secret_files": secret_count,
                    "files": files,
                }
                self._write_manifest(temporary / "manifest.json", manifest)
                os.replace(temporary, final)
                backup = self._validate(final)
                self._trim({backup_id, *(protected or set())})
            except Exception:
                shutil.rmtree(temporary, ignore_errors=True)
                self._audit(actor, "state.backup.create", "failed")
                raise
        self._audit(actor, "state.backup.create", "success", backup.public())
        return backup

    def restore(
        self,
        actor: Actor,
        backup_id: str,
        confirmation: str,
    ) -> dict:
        self._require_admin(actor)
        if not _BACKUP_ID.fullmatch(str(backup_id)):
            raise ValueError("backup identifier is invalid")
        if str(confirmation) != str(backup_id):
            raise ValueError("restore confirmation must match the backup identifier")
        with self._lock, self.database.maintenance():
            source = self.backup_directory / str(backup_id)
            backup = self._validate(source)
            safety = self.create(actor, protected={str(backup_id)})
            stage = self.database.path.parent / f".restore-{uuid.uuid4().hex}"
            rollback_database = (
                self.database.path.parent / f".rollback-{uuid.uuid4().hex}.db"
            )
            rollback_secrets = (
                self.database.path.parent / f".rollback-secrets-{uuid.uuid4().hex}"
            )
            stage.mkdir(mode=0o700)
            os.chmod(stage, 0o700)
            try:
                staged_database = stage / "notifinho.db"
                shutil.copyfile(source / "notifinho.db", staged_database)
                os.chmod(staged_database, 0o600)
                self._validate_database(staged_database)
                staged_secrets = stage / "secrets"
                staged_secrets.mkdir(mode=0o700)
                for item in sorted((source / "secrets").iterdir()):
                    self._copy_secret(item, staged_secrets / item.name)

                moved_database = False
                moved_secrets = False
                installed_database = False
                installed_secrets = False
                try:
                    os.replace(self.database.path, rollback_database)
                    moved_database = True
                    if self.secret_directory.exists():
                        os.replace(self.secret_directory, rollback_secrets)
                        moved_secrets = True
                    os.replace(staged_database, self.database.path)
                    installed_database = True
                    os.chmod(self.database.path, 0o600)
                    os.replace(staged_secrets, self.secret_directory)
                    installed_secrets = True
                    os.chmod(self.secret_directory, 0o700)
                    self._validate_database(self.database.path)
                    with self.database.transaction() as connection:
                        connection.execute("DELETE FROM sessions")
                except Exception:
                    if installed_database and self.database.path.exists():
                        self.database.path.unlink()
                    if moved_database and rollback_database.exists():
                        os.replace(rollback_database, self.database.path)
                    if installed_secrets and self.secret_directory.exists():
                        shutil.rmtree(self.secret_directory)
                    if moved_secrets and rollback_secrets.exists():
                        os.replace(rollback_secrets, self.secret_directory)
                    raise
                rollback_database.unlink(missing_ok=True)
                if rollback_secrets.exists():
                    shutil.rmtree(rollback_secrets)
            except Exception:
                self._audit(
                    actor,
                    "state.backup.restore",
                    "failed",
                    {"backup_id": backup_id, "safety_backup_id": safety.id},
                )
                raise
            finally:
                shutil.rmtree(stage, ignore_errors=True)
        result = {
            "restored": backup.public(),
            "safety_backup_id": safety.id,
            "sessions_revoked": True,
        }
        self._audit(actor, "state.backup.restore", "success", {
            "backup_id": backup_id,
            "safety_backup_id": safety.id,
            "sessions_revoked": True,
        })
        return result

    def _validate(self, directory: Path) -> StateBackup:
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("backup path must be a directory")
        manifest_path = directory / "manifest.json"
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise ValueError("backup manifest is invalid")
        if manifest_path.stat().st_size > 1024 * 1024:
            raise ValueError("backup manifest is too large")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (
            not isinstance(manifest, dict)
            or manifest.get("schema") != BACKUP_SCHEMA
            or manifest.get("id") != directory.name
        ):
            raise ValueError("backup manifest is invalid")
        files = manifest.get("files")
        if not isinstance(files, dict) or "notifinho.db" not in files:
            raise ValueError("backup manifest files are invalid")
        expected_names = {"notifinho.db"}
        secret_directory = directory / "secrets"
        if secret_directory.is_symlink() or not secret_directory.is_dir():
            raise ValueError("backup secret directory is invalid")
        for item in secret_directory.iterdir():
            if item.is_symlink() or not item.is_file() or not _SECRET_FILE.fullmatch(item.name):
                raise ValueError("backup contains an invalid secret file")
            expected_names.add(f"secrets/{item.name}")
        if set(files) != expected_names:
            raise ValueError("backup manifest file list does not match contents")
        size = 0
        for relative, digest in files.items():
            if not re.fullmatch(r"[0-9a-f]{64}", str(digest)):
                raise ValueError("backup manifest digest is invalid")
            path = directory / relative
            if not path.is_file() or path.is_symlink():
                raise ValueError("backup file is missing")
            if not hmac.compare_digest(self._digest(path), str(digest)):
                raise RuntimeError("backup integrity check failed")
            size += path.stat().st_size
        self._validate_database(directory / "notifinho.db")
        secret_count = int(manifest.get("secret_files", -1))
        if secret_count != len(expected_names) - 1:
            raise ValueError("backup secret count does not match contents")
        return StateBackup(
            id=directory.name,
            created_at=int(manifest["created_at"]),
            schema_version=int(manifest["database_schema"]),
            secret_files=secret_count,
            size_bytes=size,
        )

    def _snapshot_database(self, target: Path) -> None:
        with self.database.connect() as source:
            destination = sqlite3.connect(target)
            try:
                source.backup(destination)
                destination.commit()
            finally:
                destination.close()
        os.chmod(target, 0o600)
        self._validate_database(target)

    @staticmethod
    def _validate_database(path: Path) -> None:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        finally:
            connection.close()
        if integrity != "ok":
            raise RuntimeError("backup database integrity check failed")
        if version != LATEST_SCHEMA_VERSION:
            raise RuntimeError(
                f"backup database schema must be {LATEST_SCHEMA_VERSION}"
            )

    @staticmethod
    def _copy_secret(source: Path, destination: Path) -> None:
        if source.is_symlink() or not _SECRET_FILE.fullmatch(source.name):
            raise ValueError("secret backup source is invalid")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(source, flags)
        with os.fdopen(descriptor, "rb") as stream:
            details = os.fstat(stream.fileno())
            if not stat.S_ISREG(details.st_mode) or details.st_mode & 0o077:
                raise PermissionError("secret file must be regular and mode 0600")
            payload = stream.read(_MAXIMUM_SECRET_BYTES + 1)
        if len(payload) > _MAXIMUM_SECRET_BYTES:
            raise ValueError("secret file exceeds backup size limit")
        target_descriptor = os.open(
            destination,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(target_descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(destination, 0o600)

    @staticmethod
    def _write_manifest(path: Path, manifest: dict) -> None:
        descriptor = os.open(
            path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(manifest, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(path, 0o600)

    @staticmethod
    def _digest(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(128 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _prepare_directory(path: Path) -> None:
        if path.is_symlink():
            raise ValueError("backup directory must not be a symbolic link")
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(path, 0o700)

    def _trim(self, protected: set[str]) -> None:
        candidates = [
            path
            for path in sorted(self.backup_directory.iterdir(), reverse=True)
            if (
                not path.is_symlink()
                and path.is_dir()
                and _BACKUP_ID.fullmatch(path.name)
            )
        ]
        retained_unprotected = 0
        allowed_unprotected = max(0, self.retention - len(protected))
        for path in candidates:
            if path.name in protected:
                continue
            retained_unprotected += 1
            if retained_unprotected > allowed_unprotected:
                shutil.rmtree(path)

    @staticmethod
    def _require_admin(actor: Actor) -> None:
        if not actor.is_admin:
            raise PermissionError("administrator role is required")

    def _audit(self, actor, action, outcome, details=None):
        if self.audit is not None:
            try:
                self.audit.write(
                    actor,
                    action,
                    "state_backup",
                    None,
                    outcome,
                    details,
                )
            except Exception:
                self.audit.write(
                    None,
                    action,
                    "state_backup",
                    None,
                    outcome,
                    details,
                )
