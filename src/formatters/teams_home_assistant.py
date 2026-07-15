"""Microsoft Teams presentation for Home Assistant automation events."""

from __future__ import annotations

from formatters.teams_hardware import HardwareTeamsFormatter
from models import Notification
from version import VERSION


class HomeAssistantTeamsFormatter(HardwareTeamsFormatter):
    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        icon, color, state = self._status_meta(notification.status)
        facts = [
            self._fact("State", state),
            self._fact("Severity", str(metadata.get("severity", "")).title()),
            self._fact("Category", str(notification.category or "").title()),
            self._fact("Entity", metadata.get("entity_id")),
            self._fact("Device", metadata.get("device")),
            self._fact("Area", metadata.get("area")),
            self._fact("Tags", ", ".join(metadata.get("tags") or [])),
            self._fact("Event time", self._format_datetime(notification.start_time)),
        ]
        body = [
            self._teams_header(
                f"🏠 {icon} {notification.title or 'Home Assistant event'}",
                color,
                "home_assistant",
            ),
            {
                "type": "TextBlock",
                "text": f"Home Assistant • **{state}** • {str(notification.category or 'automation').title()}",
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
                    "text": self._truncate(notification.body or notification.title, 4000),
                    "weight": "Bolder",
                    "wrap": True,
                }],
            },
        ]
        facts = [fact for fact in facts if fact["value"]]
        if facts:
            body.append({"type": "FactSet", "spacing": "Medium", "facts": facts})
        link = self._truncate(metadata.get("action_link"), 1000)
        card = {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.4",
            "msteams": {"width": "Full"},
            "body": body + [{
                "type": "TextBlock",
                "text": f"FortPT Labs • Notifinho v{VERSION}",
                "isSubtle": True,
                "size": "Small",
                "separator": True,
                "wrap": True,
            }],
        }
        if link:
            card["actions"] = [{"type": "Action.OpenUrl", "title": "Open Home Assistant", "url": link}]
        return {
            "type": "message",
            "attachments": [{
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": card,
            }],
        }
