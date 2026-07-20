"""Microsoft Teams presentation for hardware-management events."""

from __future__ import annotations

from formatters.base import BaseFormatter
from models import Notification
from version import VERSION


class HardwareTeamsFormatter(BaseFormatter):
    provider = "Hardware management"

    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        icon, color, state = self._status_meta(notification.status)
        provider = metadata.get("provider") or self.provider
        title = notification.title or f"{provider} event"
        facts = [
            self._fact("State", state),
            self._fact("Severity", str(metadata.get("severity", "")).title()),
            self._fact("Host", metadata.get("system")),
            self._fact("Category", str(notification.category or "").title()),
            self._fact("Sensor", metadata.get("sensor")),
            self._fact("Registry", metadata.get("registry")),
            self._fact("Message ID", metadata.get("message_id")),
            self._fact("Origin", metadata.get("origin")),
            self._fact("Event time", self._format_datetime(notification.start_time)),
        ]
        body = [
            self._teams_header(f"🖥️ {icon} {title}", color, notification.source),
            {
                "type": "TextBlock",
                "text": f"{provider} • **{state}** • {str(notification.category or 'hardware').title()}",
                "isSubtle": True,
                "spacing": "Small",
                "wrap": True,
            },
            {
                "type": "Container",
                "style": "emphasis",
                "spacing": "Medium",
                "separator": True,
                "items": [{
                    "type": "TextBlock",
                    "text": self._truncate(notification.body or title, 4000),
                    "weight": "Bolder",
                    "wrap": True,
                }],
            },
        ]
        facts = [fact for fact in facts if fact["value"]]
        if facts:
            body.append({"type": "FactSet", "spacing": "Medium", "facts": facts})
        action = self._truncate(metadata.get("recommended_action"), 2000)
        if action:
            body.append({
                "type": "TextBlock",
                "text": f"🛠️ **Recommended action**\n{action}",
                "wrap": True,
                "separator": True,
            })
        body.append({
            "type": "TextBlock",
            "text": f"FortPT Labs • Notifinho v{VERSION}",
            "isSubtle": True,
            "size": "Small",
            "separator": True,
            "wrap": True,
        })
        card = {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.4",
            "msteams": {"width": "Full"},
            "body": body,
        }
        return {
            "type": "message",
            "attachments": [{
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": card,
            }],
        }

    def _fact(self, title: str, value) -> dict:
        return {"title": title, "value": self._truncate(value, 1000)}

    @staticmethod
    def _status_meta(status: str) -> tuple[str, str, str]:
        normalized = str(status or "").casefold()
        if normalized == "success":
            return "✅", "Good", "Resolved"
        if normalized == "failure":
            return "🚨", "Attention", "Critical"
        if normalized == "warning":
            return "⚠️", "Warning", "Warning"
        return "ℹ️", "Accent", "Information"


class RedfishTeamsFormatter(HardwareTeamsFormatter):
    provider = "Redfish"


class SupermicroTeamsFormatter(HardwareTeamsFormatter):
    provider = "Supermicro BMC"


class HPEILOTeamsFormatter(HardwareTeamsFormatter):
    provider = "HPE iLO"


class DellIDRACTeamsFormatter(HardwareTeamsFormatter):
    provider = "Dell iDRAC"
