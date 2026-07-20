"""Microsoft Teams presentation for hardware-management events."""

from __future__ import annotations

from formatters.teams_common import (
    TeamsCardData,
    TeamsCardFormatter,
    TeamsFact,
)
from models import Notification


class HardwareTeamsFormatter(TeamsCardFormatter):
    provider = "Hardware management"

    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        provider = str(metadata.get("provider") or self.provider)
        category = str(notification.category or "hardware")
        event = str(notification.title or f"{provider} event")
        severity = str(metadata.get("severity") or notification.status)
        action = self._truncate(metadata.get("recommended_action"), 2000)
        extra_body = ()
        if action:
            extra_body = (
                {
                    "type": "TextBlock",
                    "text": f"🛠️ **Recommended action**\n{action}",
                    "wrap": True,
                    "separator": True,
                },
            )

        return self._render_teams_card(
            TeamsCardData(
                source=notification.source,
                integration=provider,
                device=str(metadata.get("system") or provider),
                event=event,
                message=str(notification.body or event),
                status=notification.status,
                severity=severity,
                category=category,
                source_area=category,
                source_area_icon=self._category_icon(category),
                event_time=notification.start_time or notification.end_time,
                device_icon="🖥️",
                event_icon=self._event_icon(category, notification.status),
                details=tuple(
                    fact
                    for fact in (
                        TeamsFact("🌡️", "Sensor", metadata.get("sensor")),
                        TeamsFact("📚", "Registry", metadata.get("registry")),
                        TeamsFact("🏷️", "Message ID", metadata.get("message_id")),
                        TeamsFact("📍", "Origin", metadata.get("origin")),
                    )
                    if fact.value
                ),
                extra_body=extra_body,
            )
        )

    def _event_icon(self, category: str, status: str) -> str:
        status_icon, _color, _state = self._teams_status(status)
        return self._category_icon(category) or status_icon


class RedfishTeamsFormatter(HardwareTeamsFormatter):
    provider = "Redfish"


class SupermicroTeamsFormatter(HardwareTeamsFormatter):
    provider = "Supermicro BMC"


class HPEILOTeamsFormatter(HardwareTeamsFormatter):
    provider = "HPE iLO"


class DellIDRACTeamsFormatter(HardwareTeamsFormatter):
    provider = "Dell iDRAC"
