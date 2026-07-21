"""
Notifinho

discord.py

Discord output.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlparse

import requests

from config import config
from formatters.discord import DiscordFormatter
from formatters.discord_generic import GenericDiscordFormatter
from formatters.discord_grafana import GrafanaDiscordFormatter
from formatters.discord_hardware import (
    DellIDRACDiscordFormatter,
    HPEILODiscordFormatter,
    RedfishDiscordFormatter,
    SupermicroDiscordFormatter,
)
from formatters.discord_home_assistant import HomeAssistantDiscordFormatter
from formatters.discord_portainer import PortainerDiscordFormatter
from formatters.discord_proxmox import ProxmoxDiscordFormatter
from formatters.discord_qnap import QNAPDiscordFormatter
from formatters.discord_synology import SynologyDiscordFormatter
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

    ICON_DIR = Path(
        os.environ.get(
            "NOTIFINHO_DISCORD_ICON_DIR",
            "/notifinho/assets/icons",
        )
    )

    def __init__(self):

        self.default_formatter = GenericDiscordFormatter()

        self.source_formatters = {
            "xo": DiscordFormatter(),
            "grafana": GrafanaDiscordFormatter(),
            "portainer": PortainerDiscordFormatter(),
            "proxmox": ProxmoxDiscordFormatter(),
            "qnap": QNAPDiscordFormatter(),
            "synology": SynologyDiscordFormatter(),
            "truenas": TrueNASDiscordFormatter(),
            "unifi_drive": UniFiDriveDiscordFormatter(),
            "unifi_network": UniFiNetworkDiscordFormatter(),
            "unifi_protect": UniFiProtectDiscordFormatter(),
            "zabbix": ZabbixDiscordFormatter(),
            "redfish": RedfishDiscordFormatter(),
            "supermicro": SupermicroDiscordFormatter(),
            "hpe_ilo": HPEILODiscordFormatter(),
            "dell_idrac": DellIDRACDiscordFormatter(),
            "home_assistant": HomeAssistantDiscordFormatter(),
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

            payload = formatter._sanitize_payload(payload)

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

            icon = self._local_icon(payload, formatter)

            if icon is None:
                response = requests.post(
                    webhook,
                    json=payload,
                    timeout=15,
                )
            else:
                filename, path = icon
                payload["embeds"][0]["thumbnail"]["url"] = (
                    f"attachment://{filename}"
                )
                payload["attachments"] = [
                    {
                        "id": 0,
                        "filename": filename,
                    }
                ]
                with path.open("rb") as stream:
                    response = requests.post(
                        webhook,
                        data={
                            "payload_json": json.dumps(payload),
                        },
                        files={
                            "files[0]": (
                                filename,
                                stream,
                                "image/png",
                            )
                        },
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

    def _local_icon(self, payload, formatter):
        """Resolve a safe packaged icon for Discord multipart delivery."""

        embeds = payload.get("embeds") if isinstance(payload, dict) else None
        if not isinstance(embeds, list) or not embeds:
            return None
        thumbnail = embeds[0].get("thumbnail")
        if not isinstance(thumbnail, dict):
            return None
        url = str(thumbnail.get("url") or "")
        filename = Path(urlparse(url).path).name
        allowed = set(formatter.PRODUCT_ICONS.values())
        if filename not in allowed:
            return None
        path = self.ICON_DIR / filename
        if not path.is_file():
            log.warning(
                "Packaged Discord icon is unavailable: %s",
                filename,
            )
            return None
        return filename, path
