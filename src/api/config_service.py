"""Atomic configuration validation, backup, and replacement."""

from __future__ import annotations

import os
import shutil
import tempfile

from datetime import datetime, timezone
from pathlib import Path

import yaml

from api.schema import mask_secrets, merge_masked_secrets, validate_config


class ConfigService:
    def __init__(self, path: Path, configuration):
        self.path = Path(path)
        self.configuration = configuration

    def read_masked(self) -> dict:
        return mask_secrets(self._read())

    def validate(self, data) -> list[str]:
        try:
            candidate = merge_masked_secrets(self._read(), data)
        except ValueError as error:
            return [str(error)]
        return validate_config(candidate)

    def replace(self, data) -> Path:
        current = self._read()
        candidate = merge_masked_secrets(current, data)
        errors = validate_config(candidate)
        if errors:
            raise ValueError("; ".join(errors))
        backup_dir = self.path.parent / "backups"
        backup_dir.mkdir(mode=0o700, exist_ok=True)
        os.chmod(backup_dir, 0o700)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = backup_dir / f"config-{stamp}.yaml"
        shutil.copy2(self.path, backup)
        os.chmod(backup, 0o600)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".config-",
            suffix=".yaml",
            dir=self.path.parent,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                yaml.safe_dump(candidate, stream, sort_keys=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
            self.configuration.reload()
        except Exception:
            temporary.unlink(missing_ok=True)
            if not self.path.exists():
                with self.path.open("w", encoding="utf-8") as stream:
                    yaml.safe_dump(current, stream, sort_keys=False)
                os.chmod(self.path, 0o600)
            raise
        self._trim_backups(backup_dir)
        return backup

    def _read(self) -> dict:
        value = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        if not isinstance(value, dict):
            raise ValueError("configuration must be an object")
        return value

    @staticmethod
    def _trim_backups(directory: Path, keep: int = 10) -> None:
        backups = sorted(directory.glob("config-*.yaml"), reverse=True)
        for path in backups[keep:]:
            path.unlink(missing_ok=True)
