"""Small, migration-aware SQLite boundary for Notifinho platform state."""

from __future__ import annotations

import os
import sqlite3
import stat
import threading

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from storage.migrations import LATEST_SCHEMA_VERSION, MIGRATIONS


class Database:
    """Open short-lived SQLite connections with consistent safety settings."""

    def __init__(self, path: str | Path, timeout_seconds: float = 5.0):
        self.path = Path(path).expanduser().absolute()
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self._maintenance_lock = threading.RLock()

    def migrate(self) -> int:
        """Apply every pending schema migration transactionally and idempotently."""

        self._prepare_path()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        applied_at INTEGER NOT NULL DEFAULT (unixepoch())
                    )
                    """
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

            current = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if current > LATEST_SCHEMA_VERSION:
                raise RuntimeError(
                    f"database schema {current} is newer than supported "
                    f"schema {LATEST_SCHEMA_VERSION}"
                )
            if 0 < current < LATEST_SCHEMA_VERSION:
                self._backup_before_migration(
                    connection,
                    current,
                    LATEST_SCHEMA_VERSION,
                )
            recorded = {
                int(row["version"]): str(row["name"])
                for row in connection.execute(
                    "SELECT version, name FROM schema_migrations"
                )
            }
            for version, name, statements in MIGRATIONS:
                if version <= current:
                    if recorded.get(version) != name:
                        raise RuntimeError(
                            f"database migration {version} does not match this build"
                        )
                    continue
                connection.execute("BEGIN IMMEDIATE")
                try:
                    for statement in statements:
                        connection.execute(statement)
                    connection.execute(
                        "INSERT INTO schema_migrations(version, name) VALUES (?, ?)",
                        (version, name),
                    )
                    connection.execute(f"PRAGMA user_version = {int(version)}")
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
                current = version
        self._enforce_file_mode()
        return current

    @contextmanager
    def connect(self):
        """Yield a configured connection and always close it."""

        with self._maintenance_lock:
            self._prepare_path()
            connection = sqlite3.connect(
                self.path,
                timeout=self.timeout_seconds,
                isolation_level=None,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(
                f"PRAGMA busy_timeout = {int(self.timeout_seconds * 1000)}"
            )
            connection.execute("PRAGMA secure_delete = ON")
            try:
                yield connection
            finally:
                connection.close()
                self._enforce_file_mode()

    @contextmanager
    def maintenance(self):
        """Block new connections while state files are snapshotted or swapped."""

        with self._maintenance_lock:
            yield

    @contextmanager
    def transaction(self):
        """Yield a write transaction that commits or rolls back as one unit."""

        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    @property
    def schema_version(self) -> int:
        if not self.path.is_file():
            return 0
        with self.connect() as connection:
            return int(connection.execute("PRAGMA user_version").fetchone()[0])

    def _prepare_path(self) -> None:
        parent = self.path.parent
        if parent.is_symlink():
            raise ValueError("database directory must not be a symbolic link")
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(parent, 0o700)
        if self.path.is_symlink():
            raise ValueError("database file must not be a symbolic link")
        if not self.path.exists():
            descriptor = os.open(
                self.path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
            os.close(descriptor)
        details = self.path.stat()
        if not stat.S_ISREG(details.st_mode):
            raise ValueError("database path must be a regular file")
        self._enforce_file_mode()

    def _enforce_file_mode(self) -> None:
        if self.path.exists() and not self.path.is_symlink():
            os.chmod(self.path, 0o600)

    def _backup_before_migration(self, connection, current: int, target: int) -> Path:
        directory = self.path.parent / "schema-backups"
        directory.mkdir(mode=0o700, exist_ok=True)
        os.chmod(directory, 0o700)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        destination = directory / (
            f"notifinho-schema-{current}-before-{target}-{stamp}.db"
        )
        position = 1
        while destination.exists():
            destination = directory / (
                f"notifinho-schema-{current}-before-{target}-{stamp}-{position}.db"
            )
            position += 1
        backup = sqlite3.connect(destination)
        try:
            connection.backup(backup)
        finally:
            backup.close()
        os.chmod(destination, 0o600)
        backups = sorted(directory.glob("notifinho-schema-*.db"), reverse=True)
        for obsolete in backups[3:]:
            obsolete.unlink()
        return destination
