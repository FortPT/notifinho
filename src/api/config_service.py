"""Atomic configuration validation, backup, and replacement."""

from __future__ import annotations

import os
import shutil
import tempfile
import threading

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import yaml

from api.schema import mask_secrets, merge_masked_secrets, validate_config


class ConfigService:
    def __init__(self, path: Path, configuration):
        self.path = Path(path)
        self.configuration = configuration
        self._lock = threading.RLock()
        self._last_loaded_signature = None

    def read_masked(self) -> dict:
        return mask_secrets(self._read())

    def snapshot(self) -> dict:
        """Return an isolated server-side copy without exposing it to clients."""

        return deepcopy(self._read())

    def source_text(self) -> str:
        """Read the mounted source for server-side fingerprinting and migration."""

        return self.path.read_text(encoding="utf-8")

    def refresh(self) -> tuple[bool, list[str]]:
        """Reload an externally edited file after it passes full validation.

        The last known-good in-memory configuration remains active while an
        operator repairs malformed YAML. The WebUI still reads the mounted file
        directly and can therefore report the validation error.
        """

        with self._lock:
            try:
                signature = self._signature()
                if signature == self._last_loaded_signature:
                    return False, []
                candidate = self._read()
                errors = validate_config(candidate)
                if errors:
                    return False, errors
                self.configuration.reload()
                self._last_loaded_signature = signature
                return True, []
            except (OSError, ValueError, yaml.YAMLError) as error:
                return False, [str(error)]

    def validate(self, data) -> list[str]:
        try:
            candidate = merge_masked_secrets(self._read(), data)
        except ValueError as error:
            return [str(error)]
        return validate_config(candidate)

    def replace(self, data) -> Path:
        with self._lock:
            current = self._read()
            current_bytes = self.path.read_bytes()
            details = self.path.stat()
            mode = details.st_mode & 0o777
            candidate = merge_masked_secrets(current, data)
            errors = validate_config(candidate)
            if errors:
                raise ValueError("; ".join(errors))
            backup_dir = self.path.parent / "backups"
            backup_dir.mkdir(mode=0o700, exist_ok=True)
            os.chmod(backup_dir, 0o700)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = self._available_backup(backup_dir, stamp)
            shutil.copy2(self.path, backup)
            os.chmod(backup, mode)
            self._preserve_owner(backup, details.st_uid, details.st_gid)

            rendered = yaml.safe_dump(
                candidate,
                sort_keys=False,
            ).encode("utf-8")
            try:
                self._atomic_write(
                    rendered,
                    mode=mode,
                    uid=details.st_uid,
                    gid=details.st_gid,
                )
                self.configuration.reload()
                self._last_loaded_signature = self._signature()
            except Exception:
                self._atomic_write(
                    current_bytes,
                    mode=mode,
                    uid=details.st_uid,
                    gid=details.st_gid,
                )
                self.configuration.reload()
                self._last_loaded_signature = self._signature()
                raise
            self._trim_backups(backup_dir)
            return backup

    def _atomic_write(
        self,
        payload: bytes,
        *,
        mode: int,
        uid: int,
        gid: int,
    ) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".config-",
            suffix=".yaml",
            dir=self.path.parent,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, mode)
            self._preserve_owner(temporary, uid, gid)
            os.replace(temporary, self.path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    @staticmethod
    def _preserve_owner(path: Path, uid: int, gid: int) -> None:
        try:
            os.chown(path, uid, gid)
        except PermissionError:
            # Non-root development/test processes cannot change ownership.
            # The temporary file already belongs to the running process.
            pass

    def _read(self) -> dict:
        value = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        if not isinstance(value, dict):
            raise ValueError("configuration must be an object")
        return value

    def _signature(self) -> tuple[int, int]:
        details = self.path.stat()
        return details.st_mtime_ns, details.st_size

    @staticmethod
    def _available_backup(directory: Path, stamp: str) -> Path:
        candidate = directory / f"config-{stamp}.yaml"
        position = 1
        while candidate.exists():
            candidate = directory / f"config-{stamp}-{position}.yaml"
            position += 1
        return candidate

    @staticmethod
    def _trim_backups(directory: Path, keep: int = 10) -> None:
        backups = sorted(directory.glob("config-*.yaml"), reverse=True)
        for path in backups[keep:]:
            path.unlink(missing_ok=True)
