"""Discord presentation for Portainer Alerting events."""

from __future__ import annotations

from formatters.base import BaseFormatter
from models import Notification
from version import VERSION


class PortainerDiscordFormatter(BaseFormatter):
    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        icon, color, state_text = self._status_meta(
            notification.status,
            metadata.get("state"),
        )
        title = notification.title or "Portainer alert"
        message = notification.body or title
        embed = {
            "title": self._truncate(f"🐳 {icon} {title}", 256),
            "description": self._truncate(
                f"Portainer • **{state_text}**",
                1024,
            ),
            "color": color,
            "fields": [
                self._field("🚨 Alert message", message, False),
                self._field("📌 State", str(metadata.get("state", "")).title()),
                self._field(
                    "⚠️ Severity",
                    str(metadata.get("severity", "")).title(),
                ),
                self._field("🖥️ Instance", metadata.get("instance")),
                self._field("🧭 Source", metadata.get("alert_source")),
                self._field(
                    "🔐 Authentication",
                    metadata.get("authentication_method"),
                ),
                self._field("👤 Username", metadata.get("username")),
                self._field(
                    "🕒 Started",
                    self._format_datetime(notification.start_time),
                ),
                self._field(
                    "✅ Resolved",
                    self._format_datetime(notification.end_time),
                ),
            ],
            "footer": {"text": f"FortPT Labs\nNotifinho v{VERSION}"},
        }
        embed["fields"] = [field for field in embed["fields"] if field["value"]][
            :25
        ]
        self._set_discord_thumbnail(embed, "portainer")
        return {"embeds": [embed]}

    def _field(self, name: str, value, inline: bool = True) -> dict:
        return {
            "name": name,
            "value": self._truncate(value, 1024),
            "inline": inline,
        }

    @staticmethod
    def _status_meta(status, state) -> tuple[str, int, str]:
        normalized = str(status or "").casefold()
        state_text = str(state or "").casefold()
        if normalized == "success" or state_text == "resolved":
            return "✅", 0x2ECC71, "Resolved"
        if normalized == "failure":
            return "🚨", 0xE74C3C, "Firing"
        if normalized == "warning":
            return "⚠️", 0xF39C12, "Firing"
        return "ℹ️", 0x3498DB, state_text.title() or "Information"
