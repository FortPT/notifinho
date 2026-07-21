"""Bounded Slack Block Kit presentation for normalized notifications."""

from __future__ import annotations

from formatters.presentation import PresentationMixin
from models import Notification
from outputs.platform_common import safe_action_url


class SlackFormatter(PresentationMixin):
    """Render a generic fallback that retains source-specific event context."""

    def format(self, notification: Notification, *, include_metadata: bool = True) -> dict:
        metadata = notification.metadata or {}
        title = self._truncate(
            notification.title or notification.subject or "Notification",
            150,
        )
        source = self._truncate(
            metadata.get("provider") or notification.source or "Notifinho",
            100,
        )
        severity = self._truncate(
            metadata.get("severity") or notification.status or "information",
            64,
        )
        host = self._truncate(
            metadata.get("host")
            or metadata.get("hostname")
            or metadata.get("device")
            or metadata.get("node"),
            128,
        )
        message = self._truncate(notification.body or title, 2800)
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": title, "emoji": True},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": self._escape(message)},
            },
        ]
        fields = [
            self._field("Source", source),
            self._field("Severity", severity),
        ]
        if notification.status:
            fields.append(self._field("Status", notification.status))
        if host:
            fields.append(self._field("Host", host))
        if include_metadata and notification.category:
            fields.append(self._field("Category", notification.category))
        blocks.append({"type": "section", "fields": fields[:10]})

        event_time = metadata.get("event_time") or notification.start_time
        context = f"Notifinho • {source}"
        if event_time:
            formatted = self._format_datetime(event_time)
            if formatted:
                context += f" • {formatted}"
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": self._escape(context)[:2000]}
                ],
            }
        )

        action = safe_action_url(metadata.get("action_link"))
        if action:
            blocks.append(
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Open event",
                                "emoji": True,
                            },
                            "url": action,
                        }
                    ],
                }
            )
        return self._sanitize_payload({"text": title, "blocks": blocks[:50]})

    def _field(self, label, value):
        return {
            "type": "mrkdwn",
            "text": f"*{self._escape(label)}*\n{self._escape(value)[:1800]}",
        }

    @staticmethod
    def _escape(value) -> str:
        return (
            str(value or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
