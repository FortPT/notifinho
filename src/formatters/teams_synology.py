"""Microsoft Teams Adaptive Card presentation for Synology DSM events."""

from __future__ import annotations

from formatters.teams_common import TeamsCardData, TeamsCardFormatter, TeamsFact
from models import Notification


class SynologyTeamsFormatter(TeamsCardFormatter):
    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        title = notification.title or "Synology DSM notification"
        device = metadata.get("nas_name") or metadata.get("hostname") or "Synology NAS"
        return self._render_teams_card(
            TeamsCardData(
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
                event_icon="🔔",
                details=(
                    TeamsFact("🏷️", "Model", metadata.get("model")),
                    TeamsFact("🗂️", "Storage pool", metadata.get("storage_pool") or metadata.get("storage")),
                    TeamsFact("💾", "Volume", metadata.get("volume")),
                    TeamsFact("💽", "Disk", metadata.get("disk")),
                    TeamsFact("📦", "Package", metadata.get("package")),
                    TeamsFact("🧰", "Task", metadata.get("task")),
                    TeamsFact("👤", "User", metadata.get("username")),
                    TeamsFact("🌐", "Source IP", metadata.get("source_ip")),
                ),
            )
        )
