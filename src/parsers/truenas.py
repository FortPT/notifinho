"""
Notifinho

truenas.py

Parser for TrueNAS email notifications.
"""

from __future__ import annotations

from email.message import EmailMessage

from models import Notification


class Parser:
    """
    TrueNAS email parser.
    """

    def parse(
        self,
        message: EmailMessage,
    ) -> Notification:

        notification = Notification()

        notification.source = "truenas"

        return notification
