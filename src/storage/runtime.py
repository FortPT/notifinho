"""Opt-in runtime initialization for persistent v2 platform state."""

from __future__ import annotations

import os
import sys

from pathlib import Path

from storage.database import Database


DEFAULT_STATE_DIRECTORY = "/notifinho/config/platform-state"


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
    """Initialize platform state unless an operator explicitly disables it."""

    enabled = configuration.get("platform", "enabled", default=None)
    if enabled is False:
        return None
    database = Database(state_directory(configuration) / "notifinho.db")
    try:
        database.migrate()
    except OSError as error:
        if enabled is True:
            raise
        print(
            "WARNING: automatic WebUI state could not be initialized; "
            "the legacy notification pipeline will continue. Configure a "
            f"writable platform.state_dir to enable the WebUI ({error}).",
            file=sys.stderr,
            flush=True,
        )
        return None
    return database
