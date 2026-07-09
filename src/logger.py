"""
Notifinho

logger.py

Shared application logger.
"""

from __future__ import annotations

import logging
from pathlib import Path

from config import config
from version import APP_NAME, VERSION


LOG_LEVEL = config.get(
    "logging",
    "level",
    default="INFO",
).upper()

LOG_FILE = Path(
    config.get(
        "logging",
        "file",
        default="/notifinho/logs/notifinho.log",
    )
)

LOG_FILE.parent.mkdir(
    parents=True,
    exist_ok=True,
)

log = logging.getLogger("notifinho")

if not log.handlers:

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s"
    )

    #
    # File handler
    #

    file_handler = logging.FileHandler(
        LOG_FILE,
        encoding="utf-8",
    )

    file_handler.setFormatter(formatter)

    #
    # Console handler
    #

    console_handler = logging.StreamHandler()

    console_handler.setFormatter(formatter)

    #
    # Logger
    #

    log.addHandler(file_handler)
    log.addHandler(console_handler)

    log.setLevel(LOG_LEVEL)

    log.propagate = False


log.info("========================================")
log.info("%s %s", APP_NAME, VERSION)
log.info("Logger initialized")
log.info("========================================")
