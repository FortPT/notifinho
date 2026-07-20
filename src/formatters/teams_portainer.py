"""Microsoft Teams presentation for Portainer Alerting events."""

from __future__ import annotations

from formatters.teams_common import TeamsCardData, TeamsCardFormatter, TeamsFact
from models import Notification


class PortainerTeamsFormatter(TeamsCardFormatter):
    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        title = notification.title or "Portainer alert"
        state = metadata.get("state") or notification.status
        event_time = (
            notification.end_time
            if str(state).casefold() == "resolved" and notification.end_time
            else notification.start_time
        )
        return self._render_teams_card(
            TeamsCardData(
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
                event_icon="🔔",
                details=(
                    TeamsFact("🔐", "Authentication", metadata.get("authentication_method")),
                    TeamsFact("👤", "Username", metadata.get("username")),
                    TeamsFact("🕒", "Started", self._format_datetime(notification.start_time)),
                    TeamsFact("🏁", "Resolved", self._format_datetime(notification.end_time)),
                ),
            )
        )
