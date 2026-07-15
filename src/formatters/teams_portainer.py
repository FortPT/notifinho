"""Microsoft Teams presentation for Portainer Alerting events."""

from __future__ import annotations

from formatters.base import BaseFormatter
from models import Notification
from version import VERSION


class PortainerTeamsFormatter(BaseFormatter):
    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        icon, color, state_text = self._status_meta(
            notification.status,
            metadata.get("state"),
        )
        title = notification.title or "Portainer alert"
        facts = [
            self._fact("State", str(metadata.get("state", "")).title()),
            self._fact("Severity", str(metadata.get("severity", "")).title()),
            self._fact("Instance", metadata.get("instance")),
            self._fact("Source", metadata.get("alert_source")),
            self._fact("Authentication", metadata.get("authentication_method")),
            self._fact("Username", metadata.get("username")),
            self._fact("Started", notification.start_time),
            self._fact("Resolved", notification.end_time),
        ]
        body = [
            {
                "type": "TextBlock",
                "text": self._truncate(f"🐳 {icon} {title}", 512),
                "weight": "Bolder",
                "size": "Large",
                "color": color,
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": f"Portainer • **{state_text}**",
                "isSubtle": True,
                "spacing": "Small",
                "wrap": True,
            },
            {
                "type": "Container",
                "style": "emphasis",
                "spacing": "Medium",
                "separator": True,
                "items": [
                    {
                        "type": "TextBlock",
                        "text": self._truncate(notification.body or title, 4000),
                        "weight": "Bolder",
                        "wrap": True,
                    }
                ],
            },
        ]
        facts = [fact for fact in facts if fact["value"]]
        if facts:
            body.append(
                {
                    "type": "FactSet",
                    "spacing": "Medium",
                    "facts": facts,
                }
            )
        body.append(
            {
                "type": "TextBlock",
                "text": f"FortPT Labs • Notifinho v{VERSION}",
                "isSubtle": True,
                "size": "Small",
                "separator": True,
                "wrap": True,
            }
        )
        card = {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.4",
            "msteams": {"width": "Full"},
            "body": body,
        }
        return {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": card,
                }
            ],
        }

    def _fact(self, title: str, value) -> dict:
        return {"title": title, "value": self._truncate(value, 1000)}

    @staticmethod
    def _status_meta(status, state) -> tuple[str, str, str]:
        normalized = str(status or "").casefold()
        state_text = str(state or "").casefold()
        if normalized == "success" or state_text == "resolved":
            return "✅", "Good", "Resolved"
        if normalized == "failure":
            return "🚨", "Attention", "Firing"
        if normalized == "warning":
            return "⚠️", "Warning", "Firing"
        return "ℹ️", "Accent", state_text.title() or "Information"

    @staticmethod
    def _truncate(value, limit: int) -> str:
        text = "" if value is None else str(value).strip()
        return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."
