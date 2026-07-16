"""Microsoft Teams presentation for generic authenticated events."""

from __future__ import annotations

from formatters.base import BaseFormatter
from models import Notification
from version import VERSION


class GenericTeamsFormatter(BaseFormatter):
    """Render non-product-specific events without assuming an XO backup."""

    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        icon, color, state = self._status_meta(notification.status)
        source = str(
            metadata.get("provider") or notification.source or "Notifinho"
        ).strip()
        title = notification.title or notification.subject or "Notification"
        severity = str(
            metadata.get("severity") or notification.status or "information"
        ).title()
        facts = [
            self._fact("State", state),
            self._fact("Severity", severity),
            self._fact("Source", source),
            self._fact("Category", str(notification.category or "event").title()),
            self._fact("Host", metadata.get("host")),
            self._fact("Environment", metadata.get("environment")),
            self._fact("Event time", self._format_datetime(notification.start_time)),
        ]
        body = [
            self._teams_header(f"{icon} {title}", color, notification.source),
            {
                "type": "TextBlock",
                "text": (
                    f"{source} • **{state}** • "
                    f"{str(notification.category or 'event').title()}"
                ),
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
        link = self._truncate(metadata.get("action_link"), 1000)
        if link:
            card["actions"] = [{
                "type": "Action.OpenUrl",
                "title": "Open event",
                "url": link,
            }]
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
            return "🚨", "Attention", "Failure"
        if normalized == "warning":
            return "⚠️", "Warning", "Warning"
        return "ℹ️", "Accent", "Information"
