"""Microsoft Teams Adaptive Card formatters for native UniFi sources."""

from __future__ import annotations

from formatters.base import BaseFormatter
from formatters.unifi import (
    format_protect_event_time,
    notification_status_icon,
    protect_device_display,
)
from models import Notification
from version import VERSION


class _UniFiTeamsFormatter(BaseFormatter):
    label = "UniFi"
    application_icon = "ℹ️"

    def _payload(
        self,
        notification: Notification,
        facts: list[dict],
        url: str = "",
        action_title: str = "Open event",
    ) -> dict:
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
        body = [
            {
                "type": "TextBlock",
                "text": self._truncate(title, 512),
                "weight": "Bolder",
                "size": "Large",
                "color": self._color(notification.status),
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": self._truncate(notification.body or notification.title, 4000),
                "wrap": True,
            },
            {
                "type": "FactSet",
                "facts": [fact for fact in facts if fact.get("value")],
            },
            {
                "type": "TextBlock",
                "text": f"FortPT Labs - Notifinho v{VERSION}",
                "isSubtle": True,
                "size": "Small",
                "separator": True,
                "wrap": True,
            },
        ]
        card = {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.4",
            "msteams": {"width": "Full"},
            "body": body,
        }
        if url:
            card["actions"] = [
                {
                    "type": "Action.OpenUrl",
                    "title": action_title,
                    "url": url,
                }
            ]
        return {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "contentUrl": None,
                    "content": card,
                }
            ],
        }

    def _fact(self, title: str, value) -> dict:
        return {"title": title, "value": self._truncate(value, 1000)}

    def _color(self, status: str) -> str:
        return {
            "failure": "Attention",
            "warning": "Warning",
            "success": "Good",
            "information": "Accent",
        }.get(str(status or "").casefold(), "Accent")

    def _text(self, value) -> str:
        return "" if value is None else str(value).strip()

    def _truncate(self, value, limit: int) -> str:
        text = self._text(value)
        return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


class UniFiNetworkTeamsFormatter(_UniFiTeamsFormatter):
    label = "UniFi Network"
    application_icon = "📡"

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
        facts = [
            self._fact("🎛️ Controller", metadata.get("controller")),
            self._fact("🗂️ Category", notification.category),
            self._fact("⚠️ Severity", str(metadata.get("severity", "")).title()),
            self._fact("💻 Client", metadata.get("client_display_name")),
            self._fact("📶 Network / Wi-Fi", metadata.get("wifi_name") or metadata.get("network_name")),
            self._fact("📍 Last connected device", last_device),
            self._fact("⏱️ Duration", metadata.get("duration")),
            self._fact("📡 Wireless", metadata.get("wifi_rssi")),
        ]
        return self._payload(notification, facts)


class UniFiProtectTeamsFormatter(_UniFiTeamsFormatter):
    label = "UniFi Protect"
    application_icon = "📹"

    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        condition = " ".join(
            value
            for value in (
                self._text(metadata.get("condition_source")),
                self._text(metadata.get("condition_operator")),
            )
            if value
        )
        facts = [
            self._fact("🎯 Trigger type", metadata.get("trigger_key")),
            self._fact(
                "📷 Trigger device",
                protect_device_display(metadata.get("trigger_device")),
            ),
            self._fact(
                "🕒 Event time",
                format_protect_event_time(metadata.get("event_time")),
            ),
            self._fact("🔎 Condition", condition),
        ]
        return self._payload(notification, facts, self._text(metadata.get("event_link")))


class UniFiDriveTeamsFormatter(_UniFiTeamsFormatter):
    label = "UniFi Drive"
    application_icon = "💾"

    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        facts = [
            self._fact("🖥️ System", metadata.get("system")),
            self._fact("💾 Backup task", metadata.get("backup_task")),
            self._fact("📌 State", metadata.get("event_state")),
            self._fact("🗂️ Category", notification.category),
        ]
        return self._payload(
            notification,
            facts,
            self._text(metadata.get("action_link")),
            "Manage Backup Task",
        )
