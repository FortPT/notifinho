"""Discord presentation for generic authenticated and fallback events."""

from __future__ import annotations

from formatters.base import BaseFormatter
from models import Notification
from version import VERSION


class GenericDiscordFormatter(BaseFormatter):
    """Render non-product-specific events without assuming an XO backup."""

    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        icon, color, state = self._status_meta(notification.status)
        source = str(
            metadata.get("provider") or notification.source or "Notifinho"
        ).strip()
        title = notification.title or notification.subject or "Notification"
        severity = str(
            metadata.get("severity") or notification.status or "information"
        ).title()

        fields = [
            self._field("🚨 Event", notification.body or title, False),
            self._field("📌 State", state),
            self._field("⚠️ Severity", severity),
            self._field("🧩 Source", source),
            self._field("📁 Category", str(notification.category or "event").title()),
            self._field("🖥️ Host", metadata.get("host")),
            self._field("🏷️ Environment", metadata.get("environment")),
            self._field("🕒 Event time", self._format_datetime(notification.start_time)),
        ]
        embed = {
            "title": self._truncate(f"{icon} {title}", 256),
            "description": self._truncate(
                f"{source} • **{state}** • "
                f"{str(notification.category or 'event').title()}",
                1024,
            ),
            "color": color,
            "fields": [field for field in fields if field["value"]][:25],
            "footer": {"text": f"FortPT Labs\nNotifinho v{VERSION}"},
        }
        link = self._truncate(metadata.get("action_link"), 1000)
        if link:
            embed["url"] = link
        self._set_discord_thumbnail(embed, notification.source)
        return {"embeds": [embed]}

    def _field(self, name: str, value, inline: bool = True) -> dict:
        return {
            "name": name,
            "value": self._truncate(value, 1024),
            "inline": inline,
        }

    @staticmethod
    def _status_meta(status: str) -> tuple[str, int, str]:
        normalized = str(status or "").casefold()
        if normalized == "success":
            return "✅", 0x2ECC71, "Resolved"
        if normalized == "failure":
            return "🚨", 0xE74C3C, "Failure"
        if normalized == "warning":
            return "⚠️", 0xF39C12, "Warning"
        return "ℹ️", 0x3498DB, "Information"
