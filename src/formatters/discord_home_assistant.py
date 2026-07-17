"""Discord presentation for Home Assistant automation events."""

from __future__ import annotations

from formatters.discord_hardware import HardwareDiscordFormatter
from models import Notification
from version import VERSION


class HomeAssistantDiscordFormatter(HardwareDiscordFormatter):
    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        icon, color, state = self._status_meta(notification.status)
        category = str(notification.category or "automation").replace("_", " ").replace("-", " ").title()
        entity = metadata.get("entity_id")
        device = metadata.get("device")
        if entity == device:
            entity = ""
        retry = metadata.get("retry_seconds")
        retry_text = f"Retrying in {retry} seconds" if retry else ""
        fields = [
            self._field("📣 Event", notification.body or notification.title, False),
            self._field("📌 State", state),
            self._field("⚠️ Severity", str(metadata.get("severity", "")).title()),
            self._field("🧩 Service", metadata.get("service")),
            self._field("📟 Device", device),
            self._field("🔌 Entity", entity),
            self._field("🌐 Endpoint", metadata.get("endpoint")),
            self._field("📍 Area", metadata.get("area")),
            self._field("🔄 Retry", retry_text),
            self._field("🏷️ Tags", ", ".join(metadata.get("tags") or [])),
            self._field("🕒 Event time", self._format_datetime(notification.start_time)),
            self._field("🔗 Open Home Assistant", metadata.get("action_link"), False),
        ]
        embed = {
            "title": self._truncate(f"🏠 {icon} {notification.title or 'Home Assistant event'}", 256),
            "description": self._truncate(
                f"Home Assistant • **{state}** • {category}",
                1024,
            ),
            "color": color,
            "fields": [field for field in fields if field["value"]][:25],
            "footer": {"text": f"FortPT Labs\nNotifinho v{VERSION}"},
        }
        self._set_discord_thumbnail(embed, "home_assistant")
        return {"embeds": [embed]}
