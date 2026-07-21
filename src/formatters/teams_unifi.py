"""Microsoft Teams Adaptive Card formatters for native UniFi sources."""

from __future__ import annotations

from formatters.teams_common import TeamsCardData, TeamsCardFormatter, TeamsFact
from formatters.unifi import (
    format_protect_event_time,
    humanize_unifi_identifier,
    protect_condition_display,
    protect_device_display,
)
from models import Notification


class _UniFiTeamsFormatter(TeamsCardFormatter):
    label = "UniFi"
    application_icon = "ℹ️"
    source_name = "unifi"

    def _payload(
        self,
        notification: Notification,
        facts: list[dict],
        url: str = "",
        action_title: str = "Open event",
        source_area: str = "",
    ) -> dict:
        metadata = notification.metadata or {}
        device = (
            metadata.get("system")
            or metadata.get("controller")
            or metadata.get("client_display_name")
            or protect_device_display(metadata.get("trigger_device"))
            or self.label
        )
        details = []
        for fact in facts:
            value = fact.get("value")
            if not value:
                continue
            title = str(fact.get("title") or "Detail").strip()
            parts = title.split(maxsplit=1)
            icon = parts[0] if parts and not parts[0][0].isalnum() else "📌"
            label = parts[1] if len(parts) > 1 and icon == parts[0] else title
            if label.casefold() in {"category", "severity", "event time"}:
                continue
            details.append(TeamsFact(icon, label, value))
        title = notification.title or f"{self.label} notification"
        return self._render_teams_card(
            TeamsCardData(
                source=self.source_name,
                integration=self.label,
                device=device,
                event=title,
                message=notification.body or title,
                status=notification.status,
                state=metadata.get("event_state") or notification.status,
                severity=metadata.get("severity") or notification.status,
                category=notification.category or "system",
                source_area=source_area or notification.category or "System",
                event_time=metadata.get("event_time") or notification.start_time,
                device_icon=self.application_icon,
                source_area_icon="📍",
                event_icon="🔔",
                details=tuple(details),
                actions=(
                    ({"type": "Action.OpenUrl", "title": action_title, "url": url},)
                    if url
                    else ()
                ),
            )
        )

    def _fact(self, title: str, value) -> dict:
        return {"title": title, "value": self._truncate(value, 1000)}

    def _text(self, value) -> str:
        return "" if value is None else str(value).strip()

class UniFiNetworkTeamsFormatter(_UniFiTeamsFormatter):
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
        facts = [
            self._fact("🎛️ Controller", metadata.get("controller")),
            self._fact("🗂️ Category", notification.category),
            self._fact("⚠️ Severity", str(metadata.get("severity", "")).title()),
            self._fact("💻 Client", metadata.get("client_display_name")),
            self._fact("📶 Network / Wi-Fi", metadata.get("wifi_name") or metadata.get("network_name")),
            self._fact("📍 Last device", last_device),
            self._fact("⏱️ Duration", metadata.get("duration")),
            self._fact("📡 Wireless", metadata.get("wifi_rssi")),
        ]
        return self._payload(
            notification,
            facts,
            source_area=(
                metadata.get("wifi_name")
                or metadata.get("network_name")
                or notification.category
            ),
        )


class UniFiProtectTeamsFormatter(_UniFiTeamsFormatter):
    label = "UniFi Protect"
    application_icon = "📹"
    source_name = "unifi_protect"

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
        facts = [
            self._fact("🎯 Trigger type", trigger_label),
            self._fact(
                "📷 Trigger device",
                protect_device_display(metadata.get("trigger_device")),
            ),
            self._fact(
                "🕒 Event time",
                format_protect_event_time(metadata.get("event_time")),
            ),
            self._fact("🚨 Alarm rule", alarm_rule),
            self._fact("🔎 Condition", condition),
        ]
        return self._payload(
            notification,
            facts,
            self._text(metadata.get("event_link")),
            source_area=notification.category,
        )


class UniFiDriveTeamsFormatter(_UniFiTeamsFormatter):
    label = "UniFi Drive"
    application_icon = "💾"
    source_name = "unifi_drive"

    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        alarm_rule = self._text(metadata.get("alarm_name"))
        facts = [
            self._fact("🖥️ System", metadata.get("system")),
            self._fact("💾 Backup task", metadata.get("backup_task")),
            self._fact("🚨 Alarm rule", alarm_rule),
            self._fact("🗂️ Category", notification.category),
        ]
        return self._payload(
            notification,
            facts,
            self._text(metadata.get("action_link")),
            "Manage Backup Task",
            source_area=notification.category,
        )
