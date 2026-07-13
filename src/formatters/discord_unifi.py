"""Discord embed formatters for native UniFi sources."""

from __future__ import annotations

from formatters.base import BaseFormatter
from formatters.unifi import (
    format_protect_event_time,
    humanize_unifi_identifier,
    notification_status_icon,
    protect_condition_display,
    protect_device_display,
)
from models import Notification
from version import VERSION


class _UniFiDiscordFormatter(BaseFormatter):
    label = "UniFi"
    application_icon = "ℹ️"

    def _embed(self, notification: Notification, fields: list[dict], url: str = "") -> dict:
        metadata = notification.metadata or {}
        title = " ".join(
            (
                self.application_icon,
                notification_status_icon(
                    notification.status,
                    metadata.get("severity"),
                ),
                notification.title or f"{self.label} notification",
            )
        )
        embed = {
            "title": self._truncate(title, 256),
            "description": self._truncate(notification.body or notification.title, 2048),
            "color": self._color(notification.status),
            "fields": [field for field in fields if field.get("value")][:25],
            "footer": {"text": f"FortPT Labs\nNotifinho v{VERSION}"},
        }
        if url:
            embed["url"] = url
        return {"embeds": [embed]}

    def _field(self, name: str, value, inline: bool = True) -> dict:
        return {
            "name": name,
            "value": self._truncate(self._text(value), 1024),
            "inline": inline,
        }

    def _color(self, status: str) -> int:
        return {
            "failure": 0xE74C3C,
            "warning": 0xF39C12,
            "success": 0x2ECC71,
            "information": 0x3498DB,
        }.get(str(status or "").casefold(), 0x3498DB)

    def _text(self, value) -> str:
        return "" if value is None else str(value).strip()

    def _truncate(self, value, limit: int) -> str:
        text = self._text(value)
        return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


class UniFiNetworkDiscordFormatter(_UniFiDiscordFormatter):
    label = "UniFi Network"
    application_icon = "📡"

    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        client = metadata.get("client_display_name")
        network = metadata.get("wifi_name") or metadata.get("network_name")
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
        fields = [
            self._field("🎛️ Controller", metadata.get("controller")),
            self._field("🗂️ Category", notification.category),
            self._field("⚠️ Severity", str(metadata.get("severity", "")).title()),
            self._field("💻 Client", client),
            self._field("📶 Network / Wi-Fi", network),
            self._field("📍 Last connected device", last_device),
            self._field("⏱️ Duration", metadata.get("duration")),
            self._field("📡 Wireless", wifi_detail, False),
        ]
        return self._embed(notification, fields)


class UniFiProtectDiscordFormatter(_UniFiDiscordFormatter):
    label = "UniFi Protect"
    application_icon = "📹"

    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        alarm_rule = self._text(metadata.get("alarm_name"))
        trigger_key = self._text(metadata.get("trigger_key"))
        trigger_label = self._text(
            metadata.get("trigger_label")
        ) or humanize_unifi_identifier(trigger_key)
        condition = protect_condition_display(
            metadata.get("condition_source"),
            metadata.get("condition_operator"),
            trigger_key,
            omit_redundant=bool(alarm_rule),
        )
        fields = [
            self._field("🎯 Trigger type", trigger_label),
            self._field(
                "📷 Trigger device",
                protect_device_display(metadata.get("trigger_device")),
            ),
            self._field(
                "🕒 Event time",
                format_protect_event_time(metadata.get("event_time")),
            ),
            self._field("🚨 Alarm rule", alarm_rule, False),
            self._field("🔎 Condition", condition, False),
        ]
        return self._embed(notification, fields, self._text(metadata.get("event_link")))


class UniFiDriveDiscordFormatter(_UniFiDiscordFormatter):
    label = "UniFi Drive"
    application_icon = "💾"

    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        fields = [
            self._field("🖥️ System", metadata.get("system")),
            self._field("💾 Backup task", metadata.get("backup_task")),
            self._field("📌 State", metadata.get("event_state")),
            self._field("🗂️ Category", notification.category),
        ]
        return self._embed(notification, fields, self._text(metadata.get("action_link")))
