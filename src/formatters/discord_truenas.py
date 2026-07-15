"""Discord payload formatter for TrueNAS alerts."""

from __future__ import annotations

from formatters.base import BaseFormatter
from models import Notification
from version import VERSION


class TrueNASDiscordFormatter(BaseFormatter):
    """Create bounded Discord embeds without performing delivery."""

    EMBED_TEXT_BUDGET = 5900

    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        host = self._text(metadata.get("host") or metadata.get("hostname"))
        severity = self._text(metadata.get("severity") or "information")
        status = self._text(notification.status or "information")
        alert_count = metadata.get("alert_count") or len(notification.items or [])
        title = self._text(
            notification.title
            or metadata.get("event_title")
            or "TrueNAS notification"
        )
        message = self._text(
            notification.body
            or metadata.get("message")
            or "TrueNAS notification"
        )
        color = self._color(status)
        state_label = "Cleared" if status == "success" else status.title()

        embed = {
            "title": self._truncate(title, 256),
            "description": self._truncate(
                f"TrueNAS @ **{host or 'Unknown system'}** - **{state_label}**",
                1024,
            ),
            "color": color,
            "fields": [
                {
                    "name": "🚨 Alert message",
                    "value": self._truncate(message, 1024),
                    "inline": False,
                },
                {
                    "name": "🗄️ System",
                    "value": self._truncate(host or "Unknown", 1024),
                    "inline": True,
                },
                {
                    "name": "🗂️ Category",
                    "value": self._truncate(notification.category or "generic", 1024),
                    "inline": True,
                },
                {
                    "name": "📌 Status",
                    "value": self._truncate(state_label, 1024),
                    "inline": True,
                },
                {
                    "name": "⚠️ Severity",
                    "value": self._truncate(severity.title(), 1024),
                    "inline": True,
                },
            ],
            "footer": {"text": f"FortPT Labs\nNotifinho v{VERSION}"},
        }

        if alert_count:
            embed["fields"].append(
                {
                    "name": "🔢 Alert count",
                    "value": str(alert_count),
                    "inline": True,
                }
            )

        event_time = self._text(
            metadata.get("event_time")
            or notification.end_time
            or notification.start_time
        )
        if event_time:
            embed["fields"].append(
                {
                    "name": "🕒 Event time",
                    "value": self._format_datetime(event_time),
                    "inline": True,
                }
            )

        alerts = metadata.get("alerts") or notification.items or []
        if isinstance(alerts, list) and len(alerts) > 1:
            for index, alert in enumerate(alerts[:18], 1):
                if not isinstance(alert, dict):
                    continue
                event_type = self._text(alert.get("event_type") or "alert").title()
                alert_status = self._text(alert.get("status") or "information")
                label = "Cleared" if alert_status == "success" else event_type
                embed["fields"].append(
                    {
                        "name": self._truncate(f"{index}. {label}", 256),
                        "value": self._truncate(
                            self._text(alert.get("message") or "TrueNAS alert"),
                            1024,
                        ),
                        "inline": False,
                    }
                )

        embed["fields"] = embed["fields"][:25]
        self._set_discord_thumbnail(embed, "truenas")
        self._enforce_budget(embed)
        return {"embeds": [embed]}

    def _color(self, status: str) -> int:
        return {
            "failure": 0xE74C3C,
            "warning": 0xF39C12,
            "success": 0x2ECC71,
            "information": 0x3498DB,
        }.get(status.casefold(), 0x3498DB)

    def _enforce_budget(self, embed: dict) -> None:
        # Keep the first six operational fields; grouped detail is expendable.
        while len(embed["fields"]) > 6 and self._embed_text_size(embed) > self.EMBED_TEXT_BUDGET:
            embed["fields"].pop()
        if self._embed_text_size(embed) <= self.EMBED_TEXT_BUDGET:
            return
        message = embed["fields"][0]
        excess = self._embed_text_size(embed) - self.EMBED_TEXT_BUDGET
        value = str(message.get("value", ""))
        message["value"] = self._truncate(value, max(len(value) - excess, 1))

    def _embed_text_size(self, embed: dict) -> int:
        size = len(str(embed.get("title", ""))) + len(str(embed.get("description", "")))
        size += len(str(embed.get("footer", {}).get("text", "")))
        for field in embed.get("fields", []):
            size += len(str(field.get("name", "")))
            size += len(str(field.get("value", "")))
        return size

    def _text(self, value) -> str:
        if value is None:
            return ""
        if isinstance(value, (list, tuple, set)):
            return ", ".join(self._text(item) for item in value if self._text(item))
        return str(value).strip()
