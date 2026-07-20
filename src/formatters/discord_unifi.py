"""Discord embed formatters for native UniFi sources."""

from __future__ import annotations

from formatters.discord_common import DiscordCardData, DiscordCardFormatter, DiscordFact
from formatters.unifi import (
    humanize_unifi_identifier,
    protect_condition_display,
    protect_device_display,
)
from models import Notification


class _UniFiDiscordFormatter(DiscordCardFormatter):
    label = "UniFi"
    application_icon = "ℹ️"
    source_name = "unifi_network"

    def _payload(
        self,
        notification: Notification,
        device: str,
        source_area: str,
        details: tuple[DiscordFact, ...],
        url: str = "",
    ) -> dict:
        metadata = notification.metadata or {}
        title = notification.title or f"{self.label} notification"
        return self._render_discord_card(
            DiscordCardData(
                source=self.source_name,
                integration=self.label,
                device=device or self.label,
                event=title,
                message=notification.body or title,
                status=notification.status,
                state=metadata.get("event_state") or notification.status,
                severity=metadata.get("severity") or notification.status,
                category=notification.category or "system",
                source_area=source_area or notification.category or "System",
                event_time=metadata.get("event_time") or notification.start_time,
                device_icon=self.application_icon,
                details=details,
                url=url,
            )
        )

    @staticmethod
    def _text(value) -> str:
        return "" if value is None else str(value).strip()


class UniFiNetworkDiscordFormatter(_UniFiDiscordFormatter):
    label = "UniFi Network"
    application_icon = "📡"
    source_name = "unifi_network"

    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        last_device = " ".join(
            value
            for value in (
                self._text(metadata.get("last_device_name")),
                self._text(metadata.get("last_device_model")),
            )
            if value
        )
        wifi_detail = " / ".join(
            value
            for value in (
                self._text(metadata.get("wifi_band")),
                f"Channel {metadata.get('wifi_channel')}" if metadata.get("wifi_channel") else "",
                f"RSSI {metadata.get('wifi_rssi')}" if metadata.get("wifi_rssi") else "",
            )
            if value
        )
        controller = self._text(metadata.get("controller"))
        network = self._text(metadata.get("wifi_name") or metadata.get("network_name"))
        return self._payload(
            notification,
            controller or self._text(metadata.get("client_display_name")),
            network or notification.category,
            (
                DiscordFact("🎛️", "Controller", controller),
                DiscordFact("💻", "Client", metadata.get("client_display_name")),
                DiscordFact("📶", "Network / Wi-Fi", network),
                DiscordFact("📍", "Last device", last_device),
                DiscordFact("⏱️", "Duration", metadata.get("duration")),
                DiscordFact("📡", "Wireless", wifi_detail, False),
            ),
        )


class UniFiProtectDiscordFormatter(_UniFiDiscordFormatter):
    label = "UniFi Protect"
    application_icon = "📹"
    source_name = "unifi_protect"

    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        alarm_rule = self._text(metadata.get("alarm_name"))
        trigger_key = self._text(metadata.get("trigger_key"))
        trigger_label = self._text(metadata.get("trigger_label")) or humanize_unifi_identifier(trigger_key)
        trigger_device = protect_device_display(metadata.get("trigger_device"))
        condition = protect_condition_display(
            metadata.get("condition_source"),
            metadata.get("condition_operator"),
            trigger_key,
            omit_redundant=bool(alarm_rule),
        )
        return self._payload(
            notification,
            trigger_device or alarm_rule,
            notification.category or "Security",
            (
                DiscordFact("🎯", "Trigger type", trigger_label),
                DiscordFact("📷", "Trigger device", trigger_device),
                DiscordFact("🚨", "Alarm rule", alarm_rule, False),
                DiscordFact("🔎", "Condition", condition, False),
            ),
            self._text(metadata.get("event_link")),
        )


class UniFiDriveDiscordFormatter(_UniFiDiscordFormatter):
    label = "UniFi Drive"
    application_icon = "💾"
    source_name = "unifi_drive"

    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        system = self._text(metadata.get("system"))
        return self._payload(
            notification,
            system or self._text(metadata.get("backup_task")),
            notification.category or "Backup",
            (
                DiscordFact("🖥️", "System", system),
                DiscordFact("💾", "Backup task", metadata.get("backup_task")),
                DiscordFact("🚨", "Alarm rule", metadata.get("alarm_name"), False),
            ),
            self._text(metadata.get("action_link")),
        )
