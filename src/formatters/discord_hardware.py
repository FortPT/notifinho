"""Discord presentation for Redfish and server-management events."""

from __future__ import annotations

from formatters.base import BaseFormatter
from models import Notification
from version import VERSION


class HardwareDiscordFormatter(BaseFormatter):
    provider = "Hardware management"

    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        icon, color, state = self._status_meta(notification.status)
        provider = metadata.get("provider") or self.provider
        title = notification.title or f"{provider} event"
        fields = [
            self._field("🚨 Event", notification.body or title, False),
            self._field("📌 State", state),
            self._field("⚠️ Severity", str(metadata.get("severity", "")).title()),
            self._field("🖥️ System", metadata.get("system")),
            self._field("📁 Category", str(notification.category or "").title()),
            self._field("🌡️ Sensor", metadata.get("sensor")),
            self._field("📚 Registry", metadata.get("registry")),
            self._field("🏷️ Message ID", metadata.get("message_id")),
            self._field("📍 Origin", metadata.get("origin")),
            self._field("🛠️ Recommended action", metadata.get("recommended_action"), False),
            self._field("🕒 Event time", self._format_datetime(notification.start_time)),
        ]
        embed = {
            "title": self._truncate(f"🖥️ {icon} {title}", 256),
            "description": self._truncate(
                f"{provider} • **{state}** • {str(notification.category or 'hardware').title()}",
                1024,
            ),
            "color": color,
            "fields": [field for field in fields if field["value"]][:25],
            "footer": {"text": f"FortPT Labs\nNotifinho v{VERSION}"},
        }
        self._set_discord_thumbnail(embed, notification.source)
        return {"embeds": [embed]}

    def _field(self, name: str, value, inline: bool = True) -> dict:
        return {"name": name, "value": self._truncate(value, 1024), "inline": inline}

    @staticmethod
    def _status_meta(status: str) -> tuple[str, int, str]:
        normalized = str(status or "").casefold()
        if normalized == "success":
            return "✅", 0x2ECC71, "Resolved"
        if normalized == "failure":
            return "🚨", 0xE74C3C, "Critical"
        if normalized == "warning":
            return "⚠️", 0xF39C12, "Warning"
        return "ℹ️", 0x3498DB, "Information"


class RedfishDiscordFormatter(HardwareDiscordFormatter):
    provider = "Redfish"


class SupermicroDiscordFormatter(HardwareDiscordFormatter):
    provider = "Supermicro BMC"


class HPEILODiscordFormatter(HardwareDiscordFormatter):
    provider = "HPE iLO"


class DellIDRACDiscordFormatter(HardwareDiscordFormatter):
    provider = "Dell iDRAC"
