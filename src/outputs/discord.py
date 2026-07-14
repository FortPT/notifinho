"""
Notifinho

discord.py

Discord output.
"""

from __future__ import annotations

import requests

from config import config
from formatters.discord import DiscordFormatter
from formatters.discord_grafana import GrafanaDiscordFormatter
from formatters.discord_portainer import PortainerDiscordFormatter
from formatters.discord_qnap import QNAPDiscordFormatter
from formatters.discord_truenas import TrueNASDiscordFormatter
from formatters.discord_unifi import (
    UniFiDriveDiscordFormatter,
    UniFiNetworkDiscordFormatter,
    UniFiProtectDiscordFormatter,
)
from formatters.discord_zabbix import ZabbixDiscordFormatter
from logger import log
from models import Notification


class DiscordOutput:

    def __init__(self):

        self.default_formatter = DiscordFormatter()

        self.source_formatters = {
            "grafana": GrafanaDiscordFormatter(),
            "portainer": PortainerDiscordFormatter(),
            "qnap": QNAPDiscordFormatter(),
            "truenas": TrueNASDiscordFormatter(),
            "unifi_drive": UniFiDriveDiscordFormatter(),
            "unifi_network": UniFiNetworkDiscordFormatter(),
            "unifi_protect": UniFiProtectDiscordFormatter(),
            "zabbix": ZabbixDiscordFormatter(),
        }

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
                "Failed to format Discord notification."
            )

            return False

        log.info(
            "Sending notification to Discord (%s)...",
            target,
        )

        log.info(
            "Discord formatter: %s",
            formatter.__class__.__name__,
        )

        if source.startswith("unifi_"):

            log.info(
                "%s formatter selected",
                formatter.label,
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
