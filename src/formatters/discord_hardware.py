"""Discord presentation for Redfish and server-management events."""

from __future__ import annotations

from formatters.discord_common import DiscordCardData, DiscordCardFormatter, DiscordFact
from models import Notification


class HardwareDiscordFormatter(DiscordCardFormatter):
    provider = "Hardware management"

    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        provider = str(metadata.get("provider") or self.provider)
        category = str(notification.category or "hardware")
        event = str(notification.title or f"{provider} event")
        severity = str(metadata.get("severity") or notification.status)
        return self._render_discord_card(
            DiscordCardData(
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
                event_icon=self._category_icon(category),
                details=(
                    DiscordFact("🌡️", "Sensor", metadata.get("sensor")),
                    DiscordFact("📚", "Registry", metadata.get("registry")),
                    DiscordFact("🏷️", "Message ID", metadata.get("message_id")),
                    DiscordFact("🌐", "Source IP", metadata.get("source_ip")),
                    DiscordFact("📍", "Origin", metadata.get("origin"), False),
                    DiscordFact("🛠️", "Recommended action", metadata.get("recommended_action"), False),
                ),
            )
        )


class RedfishDiscordFormatter(HardwareDiscordFormatter):
    provider = "Redfish"


class SupermicroDiscordFormatter(HardwareDiscordFormatter):
    provider = "Supermicro BMC"


class HPEILODiscordFormatter(HardwareDiscordFormatter):
    provider = "HPE iLO"


class DellIDRACDiscordFormatter(HardwareDiscordFormatter):
    provider = "Dell iDRAC"
