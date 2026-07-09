"""
Notifinho

proxmox.py

Parser for Proxmox email notifications.
"""

from __future__ import annotations

from email.message import EmailMessage

from models import Notification


class Parser:
    """
    Proxmox email parser.
    """

    def parse(
        self,
        message: EmailMessage,
    ) -> Notification:

        notification = Notification()

        notification.source = "proxmox"

        return notification
