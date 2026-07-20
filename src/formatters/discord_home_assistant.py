"""Discord presentation for Home Assistant automation events."""

from __future__ import annotations

from formatters.discord_common import DiscordCardData, DiscordCardFormatter, DiscordFact
from models import Notification


class HomeAssistantDiscordFormatter(DiscordCardFormatter):
    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        entity = metadata.get("entity_id")
        device = metadata.get("device")
        if entity == device:
            entity = ""
        retry = metadata.get("retry_seconds")
        retry_text = f"Retrying in {retry} seconds" if retry else ""
        title = notification.title or "Home Assistant event"
        return self._render_discord_card(
            DiscordCardData(
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
                event_icon="🤖",
                details=(
                    DiscordFact("⚙️", "Service", metadata.get("service")),
                    DiscordFact("🔗", "Entity", entity),
                    DiscordFact("🌐", "Endpoint", metadata.get("endpoint"), False),
                    DiscordFact("❌", "Error", metadata.get("error_code")),
                    DiscordFact("🔁", "Retry", retry_text),
                    DiscordFact("🏷️", "Tags", ", ".join(metadata.get("tags") or []), False),
                ),
                url=metadata.get("action_link") or "",
            )
        )
