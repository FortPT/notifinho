"""
Notifinho

base.py

Base output interface.
"""

from __future__ import annotations

from models import Notification


class BaseOutput:

    def send(
        self,
        notification: Notification,
        target: str,
    ) -> bool:

        raise NotImplementedError
