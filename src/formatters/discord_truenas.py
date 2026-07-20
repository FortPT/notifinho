"""Discord payload formatter for TrueNAS alerts."""

from __future__ import annotations

from formatters.discord_common import DiscordCardData, DiscordCardFormatter, DiscordFact
from models import Notification


class TrueNASDiscordFormatter(DiscordCardFormatter):
    """Create bounded TrueNAS embeds without performing delivery."""

    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        host = self._text(metadata.get("host") or metadata.get("hostname"))
        severity = self._text(metadata.get("severity") or notification.status or "information")
        event = self._text(notification.title or metadata.get("event_title") or "TrueNAS notification")
        message = self._text(notification.body or metadata.get("message") or event)
        event_time = self._text(
            metadata.get("event_time") or notification.end_time or notification.start_time
        )
        details = []
        alert_count = metadata.get("alert_count") or len(notification.items or [])
        if alert_count:
            details.append(DiscordFact("🔢", "Alert count", alert_count))

        alerts = metadata.get("alerts") or notification.items or []
        if isinstance(alerts, list) and len(alerts) > 1:
            for index, alert in enumerate(alerts[:17], 1):
                if not isinstance(alert, dict):
                    continue
                event_type = self._text(alert.get("event_type") or "alert").title()
                label = "Cleared" if alert.get("status") == "success" else event_type
                details.append(
                    DiscordFact(
                        "📋",
                        f"Related alert {index} • {label}",
                        self._text(alert.get("message") or "TrueNAS alert"),
                        False,
                    )
                )

        status = notification.status
        return self._render_discord_card(
            DiscordCardData(
                source="truenas",
                integration="TrueNAS",
                device=host or "TrueNAS",
                event=event,
                message=message,
                status=status,
                state="cleared" if status == "success" else status,
                severity=severity,
                category=notification.category or "storage",
                source_area=metadata.get("source") or notification.category or "System",
                event_time=event_time,
                device_icon="🗄️",
                source_area_icon="⚙️",
                details=tuple(details),
            )
        )

    @staticmethod
    def _text(value) -> str:
        if value is None:
            return ""
        if isinstance(value, (list, tuple, set)):
            return ", ".join(str(item).strip() for item in value if str(item).strip())
        return str(value).strip()
