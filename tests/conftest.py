"""Shared pytest bootstrap for Notifinho unit tests.

Tests deliberately avoid importing the private ``config/config.yaml`` or
writing production logs. The application modules use top-level imports from
``src``, so this bootstrap provides a minimal public configuration and a
standard-library logger before those modules are collected.
"""

from __future__ import annotations

import logging
import sys

from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

sys.path.insert(
    0,
    str(SRC),
)


class TestConfig:
    """Small config provider matching the application's ``get`` API."""

    __test__ = False

    def __init__(self):

        self._data = {
            "notifications": {
                "xo": {
                    "show_ids": False,
                },
                "zabbix": {
                    "show_ids": False,
                },
            },
        }

    def get(
        self,
        *keys,
        default=None,
    ):

        value = self._data

        for key in keys:

            if not isinstance(value, dict):

                return default

            value = value.get(
                key,
            )

            if value is None:

                return default

        return value


config_module = ModuleType(
    "config",
)

config_module.config = TestConfig()

sys.modules["config"] = config_module


logger_module = ModuleType(
    "logger",
)

logger_module.log = logging.getLogger(
    "notifinho.tests",
)

sys.modules["logger"] = logger_module
