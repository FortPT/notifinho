"""Discord presentation for normalized Synology DSM events."""

from __future__ import annotations

from formatters.discord_common import DiscordCardData, DiscordCardFormatter, DiscordFact
from models import Notification


class SynologyDiscordFormatter(DiscordCardFormatter):
    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        title = notification.title or "Synology DSM notification"
        device = metadata.get("nas_name") or metadata.get("hostname") or "Synology NAS"
        return self._render_discord_card(
            DiscordCardData(
                source="synology",
                integration="Synology DSM",
                device=device,
                event=title,
                message=notification.body or title,
                status=notification.status,
                severity=metadata.get("severity") or notification.status,
                category=notification.category or "storage",
                source_area=metadata.get("package") or notification.category or "System",
                event_time=metadata.get("event_time") or notification.start_time,
                device_icon="🗄️",
                source_area_icon="⚙️",
                details=(
                    DiscordFact("🏷️", "Model", metadata.get("model")),
                    DiscordFact("🗂️", "Storage pool", metadata.get("storage_pool") or metadata.get("storage")),
                    DiscordFact("💾", "Volume", metadata.get("volume")),
                    DiscordFact("💽", "Disk", metadata.get("disk")),
                    DiscordFact("📦", "Package", metadata.get("package")),
                    DiscordFact("🧰", "Task", metadata.get("task")),
                    DiscordFact("👤", "User", metadata.get("username")),
                    DiscordFact("🌐", "Source IP", metadata.get("source_ip")),
                ),
            )
        )
