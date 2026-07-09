"""
Notifinho

discord.py

Discord output.
"""

from __future__ import annotations

import requests

from config import config
from logger import log
from models import Notification

from formatters.discord import DiscordFormatter


class DiscordOutput:

    def __init__(self):

        self.formatter = DiscordFormatter()

    def send(
        self,
        notification: Notification,
        target: str = "default",
    ) -> bool:

        webhook = config.get(
            "outputs",
            "discord",
            target,
            "webhook",
        )

        if not webhook:

            log.error(
                "Discord webhook not configured for '%s'.",
                target,
            )

            return False

        payload = self.formatter.format(
            notification,
        )

        log.info(
            "Sending notification to Discord (%s)...",
            target,
        )

        log.info(
            "Webhook ID: %s",
            webhook.split("/")[-2],
        )

        try:

            response = requests.post(
                webhook,
                json=payload,
                timeout=15,
            )

            if response.status_code >= 400:

                log.error(
                    "Discord returned %s",
                    response.status_code,
                )

                log.error(
                    "Discord response: %s",
                    response.text,
                )

                return False

            log.info(
                "Discord notification sent successfully."
            )

            return True

        except Exception:

            log.exception(
                "Failed to send Discord notification."
            )

            return False
