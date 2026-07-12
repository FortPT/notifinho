"""
Notifinho

teams.py

Microsoft Teams output.
"""

from __future__ import annotations

import requests

from config import config
from formatters.teams import TeamsFormatter
from formatters.teams_grafana import GrafanaTeamsFormatter
from formatters.teams_qnap import QNAPTeamsFormatter
from formatters.teams_truenas import TrueNASTeamsFormatter
from formatters.teams_zabbix import ZabbixTeamsFormatter
from logger import log
from models import Notification


class TeamsOutput:

    def __init__(self):

        self.default_formatter = TeamsFormatter()

        self.source_formatters = {
            "grafana": GrafanaTeamsFormatter(),
            "qnap": QNAPTeamsFormatter(),
            "truenas": TrueNASTeamsFormatter(),
            "zabbix": ZabbixTeamsFormatter(),
        }

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

        source = (
            notification.source
            or ""
        ).lower()

        formatter = self.source_formatters.get(
            source,
            self.default_formatter,
        )

        try:

            payload = formatter.format(
                notification,
            )

        except Exception:

            log.exception(
                "Failed to format Teams notification."
            )

            return False

        log.info(
            "Sending notification to Microsoft Teams (%s)...",
            target,
        )

        log.info(
            "Teams formatter: %s",
            formatter.__class__.__name__,
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

            log.info(
                "Teams notification sent successfully."
            )

            return True

        except Exception:

            log.exception(
                "Failed to send Teams notification."
            )

            return False
