"""Discord presentation for Portainer Alerting events."""

from __future__ import annotations

from formatters.discord_common import DiscordCardData, DiscordCardFormatter, DiscordFact
from models import Notification


class PortainerDiscordFormatter(DiscordCardFormatter):
    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        title = notification.title or "Portainer alert"
        state = metadata.get("state") or notification.status
        event_time = (
            notification.end_time
            if str(state).casefold() == "resolved" and notification.end_time
            else notification.start_time
        )
        return self._render_discord_card(
            DiscordCardData(
                source="portainer",
                integration="Portainer",
                device=metadata.get("instance") or "Portainer",
                event=title,
                message=notification.body or title,
                status=notification.status,
                state=state,
                severity=metadata.get("severity") or notification.status,
                category=notification.category or "containers",
                source_area=metadata.get("alert_source") or "Containers",
                event_time=event_time,
                device_icon="🐳",
                source_area_icon="📦",
                details=(
                    DiscordFact("🔐", "Authentication", metadata.get("authentication_method")),
                    DiscordFact("👤", "Username", metadata.get("username")),
                    DiscordFact("🕒", "Started", self._format_datetime(notification.start_time)),
                    DiscordFact("🏁", "Resolved", self._format_datetime(notification.end_time)),
                ),
            )
        )
