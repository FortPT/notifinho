"""Discord presentation for normalized Proxmox VE events."""

from __future__ import annotations

from formatters.base import BaseFormatter
from models import Notification
from version import VERSION


class ProxmoxDiscordFormatter(BaseFormatter):
    CATEGORY_ICONS = {
        "backup": "💾",
        "replication": "🔁",
        "storage": "🗄️",
        "cluster": "🧩",
        "availability": "📡",
        "security": "🔐",
        "guest": "🖥️",
        "system": "⚙️",
        "generic": "🔔",
    }

    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        icon, color, state = self._status(notification.status)
        category = notification.category or metadata.get("category") or "generic"
        title = notification.title or "Proxmox VE notification"
        fields = [
            self._field("📣 Event", notification.body or title, False),
            self._field("📌 State", state),
            self._field("⚠️ Severity", self._label(metadata.get("severity"))),
            self._field("🖧 Node", metadata.get("node") or metadata.get("host")),
            self._field("🔢 VMID", metadata.get("vmid")),
            self._field("🖥️ Guest", metadata.get("guest")),
            self._field("🧰 Job", metadata.get("job_id")),
            self._field("🗄️ Storage", metadata.get("storage")),
            self._field("🕒 Event time", metadata.get("event_time") or notification.start_time),
            self._field("⏱️ Duration", notification.duration),
        ]
        if notification.vm_total:
            fields.extend(
                (
                    self._field("✅ Guests OK", notification.vm_success),
                    self._field("❌ Guests failed", notification.vm_failed),
                )
            )
        if notification.failed_vms:
            fields.append(
                self._field(
                    "❌ Failed guests",
                    "\n".join(notification.failed_vms),
                    False,
                )
            )
        if notification.errors:
            fields.append(
                self._field(
                    "🚨 Error details",
                    "\n".join(notification.errors),
                    False,
                )
            )
        if notification.successful_vms:
            fields.append(
                self._field(
                    "✅ Successful guests",
                    "\n".join(notification.successful_vms),
                    False,
                )
            )
        embed = {
            "title": self._truncate(f"🟧 {icon} {title}", 256),
            "description": self._truncate(
                f"Proxmox VE • **{state}** • "
                f"{self.CATEGORY_ICONS.get(category, '🔔')} {self._label(category)}",
                1024,
            ),
            "color": color,
            "fields": [field for field in fields if field["value"]][:25],
            "footer": {"text": f"FortPT Labs\nNotifinho v{VERSION}"},
        }
        return {"embeds": [embed]}

    def _field(self, name: str, value, inline: bool = True) -> dict:
        return {"name": name, "value": self._truncate(value, 1024), "inline": inline}

    @staticmethod
    def _status(value: str) -> tuple[str, int, str]:
        status = str(value or "").casefold()
        if status == "failure":
            return "🚨", 0xE74C3C, "Failed"
        if status == "warning":
            return "⚠️", 0xF39C12, "Warning"
        if status == "success":
            return "✅", 0x2ECC71, "Success"
        return "ℹ️", 0x3498DB, "Information"

    @staticmethod
    def _label(value) -> str:
        return str(value or "").replace("_", " ").strip().title()

    @staticmethod
    def _truncate(value, limit: int) -> str:
        text = "" if value is None else str(value).strip()
        return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."
