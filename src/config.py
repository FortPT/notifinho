"""
Notifinho

config.py

Loads and provides access to the application
configuration.
"""

from __future__ import annotations

from pathlib import Path
from copy import deepcopy
from threading import RLock

import yaml


#
# Project root
#
# /notifinho
#

BASE_DIR = Path(__file__).resolve().parent.parent

#
# Configuration file
#
# /notifinho/config/config.yaml
#

CONFIG_FILE = BASE_DIR / "config" / "config.yaml"


class Config:
    """
    Application configuration.
    """

    def __init__(self):

        self._data = {}

        self._lock = RLock()

        self.reload()

    def reload(self):
        """
        Reload configuration from disk.
        """

        with open(CONFIG_FILE, "r", encoding="utf-8") as f:

            loaded = yaml.safe_load(f) or {}

        if not isinstance(loaded, dict):

            raise ValueError("configuration must be an object")

        with self._lock:

            self._data = loaded

    def get(self, *keys, default=None):
        """
        Read a configuration value.

        Example:

            config.get("routing", "xo")

        Returns None (or default) if any key is missing.
        """

        with self._lock:

            value = self._data

            for key in keys:

                if not isinstance(value, dict):

                    return default

                value = value.get(key)

                if value is None:

                    return default

            return deepcopy(value)

    def snapshot(self):
        """Return an isolated copy for validation and masked API responses."""

        with self._lock:

            return deepcopy(self._data)


config = Config()
