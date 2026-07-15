"""Microsoft Teams Adaptive Card presentation for Synology DSM events."""

from __future__ import annotations

from formatters.base import BaseFormatter
from models import Notification
from version import VERSION


class SynologyTeamsFormatter(BaseFormatter):
    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        icon, color, state = self._status(notification.status)
        title = notification.title or "Synology DSM notification"
        facts = [
            self._fact("State", state),
            self._fact("Severity", self._label(metadata.get("severity"))),
            self._fact("Category", self._label(notification.category)),
            self._fact(
                "NAS",
                metadata.get("nas_name") or metadata.get("hostname"),
            ),
            self._fact("Model", metadata.get("model")),
            self._fact(
                "Storage pool",
                metadata.get("storage_pool") or metadata.get("storage"),
            ),
            self._fact("Volume", metadata.get("volume")),
            self._fact("Disk", metadata.get("disk")),
            self._fact("Package", metadata.get("package")),
            self._fact("Task", metadata.get("task")),
            self._fact("User", metadata.get("username")),
            self._fact("Source IP", metadata.get("source_ip")),
            self._fact(
                "Event time",
                metadata.get("event_time") or notification.start_time,
            ),
        ]
        body = [
            {
                "type": "TextBlock",
                "text": self._truncate(f"🗄️ {icon} {title}", 512),
                "weight": "Bolder",
                "size": "Large",
                "color": color,
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": f"Synology DSM • **{state}**",
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
        return {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "msteams": {"width": "Full"},
                        "body": body,
                    },
                }
            ],
        }

    def _fact(self, title: str, value) -> dict:
        return {"title": title, "value": self._truncate(value, 1000)}

    @staticmethod
    def _status(value: str) -> tuple[str, str, str]:
        status = str(value or "").casefold()
        if status == "failure":
            return "🚨", "Attention", "Failed"
        if status == "warning":
            return "⚠️", "Warning", "Warning"
        if status == "success":
            return "✅", "Good", "Resolved"
        return "ℹ️", "Accent", "Information"

    @staticmethod
    def _label(value) -> str:
        return str(value or "").replace("_", " ").strip().title()

    @staticmethod
    def _truncate(value, limit: int) -> str:
        text = "" if value is None else str(value).strip()
        return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."
