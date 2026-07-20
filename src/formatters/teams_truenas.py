"""Microsoft Teams Adaptive Card formatter for TrueNAS alerts."""

from __future__ import annotations

from formatters.teams_common import TeamsCardData, TeamsCardFormatter, TeamsFact
from models import Notification


class TrueNASTeamsFormatter(TeamsCardFormatter):
    """Create a bounded Teams Adaptive Card without delivery logic."""

    TEXT_LIMIT = 16000

    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        host = self._text(metadata.get("host") or metadata.get("hostname"))
        severity = self._text(metadata.get("severity") or "information")
        message = self._truncate(
            self._text(notification.body or metadata.get("message") or "TrueNAS notification"),
            4000,
        )
        details = []
        alert_count = metadata.get("alert_count") or len(notification.items or [])
        if alert_count:
            details.append(TeamsFact("🔢", "Alert count", alert_count))
        event_time = self._text(
            metadata.get("event_time") or notification.end_time or notification.start_time
        )
        extra_body = []
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
                extra_body.append(
                    {
                        "type": "Container",
                        "spacing": "Medium",
                        "separator": True,
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": "📋 Related alerts",
                                "weight": "Bolder",
                                "wrap": True,
                            },
                            *detail_items,
                        ],
                    }
                )
        event = notification.title or metadata.get("event_title") or "TrueNAS notification"
        payload = self._render_teams_card(
            TeamsCardData(
                source="truenas",
                integration="TrueNAS",
                device=host or "TrueNAS",
                event=event,
                message=message,
                status=notification.status,
                state="cleared" if notification.status == "success" else notification.status,
                severity=severity,
                category=notification.category or "storage",
                source_area=metadata.get("source") or notification.category or "System",
                event_time=event_time,
                device_icon="🗄️",
                source_area_icon="⚙️",
                event_icon="🔔",
                details=tuple(details),
                extra_body=tuple(extra_body),
            )
        )
        card = payload["attachments"][0]["content"]
        self._enforce_budget(card)
        return payload

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
