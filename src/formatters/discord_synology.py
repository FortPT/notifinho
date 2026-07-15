"""Discord presentation for normalized Synology DSM events."""

from __future__ import annotations

from formatters.base import BaseFormatter
from models import Notification
from version import VERSION


class SynologyDiscordFormatter(BaseFormatter):
    CATEGORY_ICONS = {
        "availability": "📡",
        "backup": "💾",
        "disk": "💿",
        "network": "🌐",
        "package": "📦",
        "power": "🔌",
        "replication": "🔁",
        "security": "🔐",
        "storage": "🗄️",
        "system": "⚙️",
        "generic": "🔔",
    }

    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        icon, color, state = self._status(notification.status)
        category = notification.category or metadata.get("category") or "generic"
        title = notification.title or "Synology DSM notification"
        fields = [
            self._field("📣 Event", notification.body or title, False),
            self._field("📌 State", state),
            self._field("⚠️ Severity", self._label(metadata.get("severity"))),
            self._field(
                "🗄️ NAS",
                metadata.get("nas_name") or metadata.get("hostname"),
            ),
            self._field("🧰 Model", metadata.get("model")),
            self._field(
                "🗂️ Storage pool",
                metadata.get("storage_pool") or metadata.get("storage"),
            ),
            self._field("💾 Volume", metadata.get("volume")),
            self._field("💿 Disk", metadata.get("disk")),
            self._field("📦 Package", metadata.get("package")),
            self._field("📋 Task", metadata.get("task")),
            self._field("👤 User", metadata.get("username")),
            self._field("🌐 Source IP", metadata.get("source_ip")),
            self._field(
                "🕒 Event time",
                metadata.get("event_time") or notification.start_time,
            ),
        ]
        embed = {
            "title": self._truncate(f"🗄️ {icon} {title}", 256),
            "description": self._truncate(
                f"Synology DSM • **{state}** • "
                f"{self.CATEGORY_ICONS.get(category, '🔔')} "
                f"{self._label(category)}",
                1024,
            ),
            "color": color,
            "fields": [field for field in fields if field["value"]][:25],
            "footer": {"text": f"FortPT Labs\nNotifinho v{VERSION}"},
        }
        return {"embeds": [embed]}

    def _field(self, name: str, value, inline: bool = True) -> dict:
        return {
            "name": name,
            "value": self._truncate(value, 1024),
            "inline": inline,
        }

    @staticmethod
    def _status(value: str) -> tuple[str, int, str]:
        status = str(value or "").casefold()
        if status == "failure":
            return "🚨", 0xE74C3C, "Failed"
        if status == "warning":
            return "⚠️", 0xF39C12, "Warning"
        if status == "success":
            return "✅", 0x2ECC71, "Resolved"
        return "ℹ️", 0x3498DB, "Information"

    @staticmethod
    def _label(value) -> str:
        return str(value or "").replace("_", " ").strip().title()

    @staticmethod
    def _truncate(value, limit: int) -> str:
        text = "" if value is None else str(value).strip()
        return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."
