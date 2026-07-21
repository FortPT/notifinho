"""Opt-in runtime initialization for persistent v2 platform state."""

from __future__ import annotations

import os

from pathlib import Path

from storage.database import Database


DEFAULT_STATE_DIRECTORY = "/notifinho/state"


def state_directory(configuration) -> Path:
    configured = os.environ.get("NOTIFINHO_STATE_DIR") or configuration.get(
        "platform",
        "state_dir",
        default=DEFAULT_STATE_DIRECTORY,
    )
    path = Path(str(configured or "")).expanduser()
    if not path.is_absolute():
        raise ValueError("platform.state_dir must be an absolute path")
    if path == Path("/"):
        raise ValueError("platform.state_dir must not be the filesystem root")
    return path


def initialize_state(configuration) -> Database | None:
    """Migrate platform state only when the unfinished v2 layer is enabled."""

    if configuration.get("platform", "enabled", default=False) is not True:
        return None
    database = Database(state_directory(configuration) / "notifinho.db")
    database.migrate()
    return database
