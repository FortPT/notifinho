"""
Notifinho

teams.py

Microsoft Teams output.
"""

from __future__ import annotations

import requests

from config import config
from logger import log
from models import Notification
from formatters.teams import TeamsFormatter


class TeamsOutput:

    def __init__(self):
        self.formatter = TeamsFormatter()

    def send(
        self,
        notification: Notification,
        target: str = "default",
    ) -> bool:

        webhook = config.get(
            "outputs",
            "teams",
            target,
            "webhook",
        )

        if not webhook:
            log.error(
                "Teams webhook not configured for '%s'.",
                target,
            )
            return False

        try:
            payload = self.formatter.format(notification)

        except NotImplementedError:
            log.error("Teams formatter is not implemented yet.")
            return False

        except Exception:
            log.exception("Failed to format Teams notification.")
            return False

        log.info(
            "Sending notification to Microsoft Teams (%s)...",
            target,
        )

        try:
            response = requests.post(
                webhook,
                json=payload,
                timeout=15,
            )

            if response.status_code >= 400:
                log.error(
                    "Teams returned %s",
                    response.status_code,
                )
                log.error(
                    "Teams response: %s",
                    response.text,
                )
                return False

            log.info("Teams notification sent successfully.")
            return True

        except Exception:
            log.exception("Failed to send Teams notification.")
            return False
