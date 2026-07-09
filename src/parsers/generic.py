"""
Notifinho

generic.py

Fallback parser.

Used when no platform-specific parser matches
an incoming email.
"""

from __future__ import annotations

from email.message import EmailMessage

from models import Notification


class Parser:
    """
    Generic email parser.
    """

    def parse(
        self,
        message: EmailMessage,
    ) -> Notification:

        notification = Notification()

        notification.source = "generic"

        notification.subject = message.get(
            "Subject",
            "",
        )

        notification.sender = message.get(
            "From",
            "",
        )

        notification.body = ""

        return notification
