"""Discord presentation for generic authenticated events."""

from __future__ import annotations

from formatters.discord_common import DiscordCardData, DiscordCardFormatter, DiscordFact
from models import Notification


class GenericDiscordFormatter(DiscordCardFormatter):
    """Render non-product-specific events without assuming an XO backup."""

    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        source = str(
            metadata.get("provider") or notification.source or "Notifinho"
        ).strip()
        title = notification.title or notification.subject or "Notification"
        severity = metadata.get("severity") or notification.status or "information"
        device = str(
            metadata.get("host")
            or metadata.get("device")
            or metadata.get("instance")
            or source
        ).strip()
        return self._render_discord_card(
            DiscordCardData(
                source="notifinho",
                integration=source,
                device=device,
                event=title,
                message=notification.body or title,
                status=notification.status,
                severity=str(severity),
                category=notification.category or "event",
                source_area=metadata.get("component") or notification.category or "event",
                event_time=metadata.get("event_time") or notification.start_time,
                details=(
                    DiscordFact("🌍", "Environment", metadata.get("environment")),
                    DiscordFact("📍", "Source", source),
                ),
                url=metadata.get("action_link") or "",
            )
        )
