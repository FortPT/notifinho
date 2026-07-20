"""Microsoft Teams presentation for Home Assistant automation events."""

from __future__ import annotations

from formatters.teams_common import TeamsCardData, TeamsCardFormatter, TeamsFact
from models import Notification


class HomeAssistantTeamsFormatter(TeamsCardFormatter):
    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        entity = metadata.get("entity_id")
        device = metadata.get("device")
        if entity == device:
            entity = ""
        retry = metadata.get("retry_seconds")
        retry_text = f"Retrying in {retry} seconds" if retry else ""
        link = self._truncate(metadata.get("action_link"), 1000)
        title = notification.title or "Home Assistant event"
        return self._render_teams_card(
            TeamsCardData(
                source="home_assistant",
                integration="Home Assistant",
                device=device or metadata.get("area") or "Home Assistant",
                event=title,
                message=notification.body or title,
                status=notification.status,
                state=metadata.get("state") or notification.status,
                severity=metadata.get("severity") or notification.status,
                category=notification.category or "automation",
                source_area=metadata.get("area") or "Automation",
                event_time=metadata.get("event_time") or notification.start_time,
                device_icon="🏠",
                source_area_icon="📍",
                event_icon="🤖",
                details=(
                    TeamsFact("⚙️", "Service", metadata.get("service")),
                    TeamsFact("🔗", "Entity", entity),
                    TeamsFact("🌐", "Endpoint", metadata.get("endpoint")),
                    TeamsFact("❌", "Error", metadata.get("error_code")),
                    TeamsFact("🔁", "Retry", retry_text),
                    TeamsFact("🏷️", "Tags", ", ".join(metadata.get("tags") or [])),
                ),
                actions=(
                    ({"type": "Action.OpenUrl", "title": "Open Home Assistant", "url": link},)
                    if link
                    else ()
                ),
            )
        )
