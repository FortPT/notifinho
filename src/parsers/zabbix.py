"""
Notifinho

zabbix.py

Parser for Zabbix email notifications.
"""

from __future__ import annotations

from email.message import EmailMessage

from models import Notification


class Parser:
    """
    Zabbix email parser.
    """

    def parse(
        self,
        message: EmailMessage,
    ) -> Notification:

        notification = Notification()

        notification.source = "zabbix"

        return notification
