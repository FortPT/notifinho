"""Microsoft Teams Adaptive Card formatter for TrueNAS alerts."""

from __future__ import annotations

from formatters.base import BaseFormatter
from models import Notification
from version import VERSION


class TrueNASTeamsFormatter(BaseFormatter):
    """Create a bounded Teams Adaptive Card without delivery logic."""

    TEXT_LIMIT = 16000

    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        host = self._text(metadata.get("host") or metadata.get("hostname"))
        status = self._text(notification.status or "information")
        severity = self._text(metadata.get("severity") or "information")
        state_label = "Cleared" if status == "success" else status.title()
        color = self._color(status)
        message = self._truncate(
            self._text(notification.body or metadata.get("message") or "TrueNAS notification"),
            4000,
        )
        facts = [
            {"title": "🗄️ System", "value": host or "Unknown"},
            {"title": "🗂️ Category", "value": notification.category or "generic"},
            {"title": "📌 Status", "value": state_label},
            {"title": "⚠️ Severity", "value": severity.title()},
        ]
        alert_count = metadata.get("alert_count") or len(notification.items or [])
        if alert_count:
            facts.append({"title": "🔢 Alert count", "value": str(alert_count)})
        event_time = self._text(
            metadata.get("event_time") or notification.end_time or notification.start_time
        )
        if event_time:
            facts.append(
                {
                    "title": "🕒 Event time",
                    "value": self._format_datetime(event_time),
                }
            )

        body = [
            self._teams_header(
                notification.title
                or metadata.get("event_title")
                or "TrueNAS notification",
                color,
                "truenas",
            ),
            {
                "type": "TextBlock",
                "text": f"TrueNAS @ **{host or 'Unknown system'}** - **{state_label}**",
                "isSubtle": True,
                "wrap": True,
            },
            {
                "type": "Container",
                "style": "emphasis",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": message,
                        "weight": "Bolder",
                        "wrap": True,
                    }
                ],
            },
            {"type": "FactSet", "facts": facts},
        ]

        alerts = metadata.get("alerts") or notification.items or []
        if isinstance(alerts, list) and len(alerts) > 1:
            detail_items = []
            for index, alert in enumerate(alerts[:20], 1):
                if not isinstance(alert, dict):
                    continue
                event_type = self._text(alert.get("event_type") or "alert").title()
                label = "Cleared" if alert.get("status") == "success" else event_type
                detail_items.append(
                    {
                        "type": "TextBlock",
                        "text": self._truncate(
                            f"**{index}. {label}:** {self._text(alert.get('message'))}",
                            1000,
                        ),
                        "wrap": True,
                    }
                )
            if detail_items:
                body.append(
                    {
                        "type": "Container",
                        "separator": True,
                        "items": detail_items,
                    }
                )

        body.append(
            {
                "type": "TextBlock",
                "text": f"FortPT Labs - Notifinho v{VERSION}",
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
        self._enforce_budget(card)
        return {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "contentUrl": None,
                    "content": card,
                }
            ],
        }

    def _color(self, status: str) -> str:
        return {
            "failure": "Attention",
            "warning": "Warning",
            "success": "Good",
            "information": "Accent",
        }.get(status.casefold(), "Accent")

    def _enforce_budget(self, card: dict) -> None:
        while self._text_size(card) > self.TEXT_LIMIT:
            containers = [
                item
                for item in card.get("body", [])
                if item.get("type") == "Container" and len(item.get("items", [])) > 1
            ]
            if not containers:
                break
            containers[-1]["items"].pop()

    def _text_size(self, value) -> int:
        if isinstance(value, dict):
            return sum(
                len(str(nested)) if key in {"text", "title", "value"} else self._text_size(nested)
                for key, nested in value.items()
            )
        if isinstance(value, list):
            return sum(self._text_size(item) for item in value)
        return 0

    def _text(self, value) -> str:
        return "" if value is None else str(value).strip()
