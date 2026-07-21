"""Discord presentation for Zabbix monitoring events."""

from __future__ import annotations

from config import config
from formatters.discord_common import DiscordCardData, DiscordCardFormatter, DiscordFact
from models import Notification


class ZabbixDiscordFormatter(DiscordCardFormatter):
    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        event_type = str(metadata.get("event_type", "")).casefold()
        is_recovery = event_type == "recovery" or str(notification.status).casefold() in {
            "success", "resolved", "recovery",
        }
        host = metadata.get("host") or "Unknown host"
        problem = metadata.get("problem_name") or notification.title or notification.subject or "Zabbix event"
        severity = metadata.get("severity") or "Not classified"
        details = [
            DiscordFact("📊", "Operational data", metadata.get("operational_data"), False),
            DiscordFact("⏱️", "Duration", notification.duration),
        ]
        if config.get("notifications", "zabbix", "show_ids", default=False):
            details.append(DiscordFact("🆔", "Event ID", metadata.get("problem_id")))
        return self._render_discord_card(
            DiscordCardData(
                source="zabbix",
                integration="Zabbix",
                device=host,
                event=problem,
                message=notification.body or problem,
                status="success" if is_recovery else notification.status,
                state="problem resolved" if is_recovery else "problem",
                severity=severity,
                category=notification.category or "monitoring",
                source_area=metadata.get("source") or notification.category or "Monitoring",
                event_time=metadata.get("event_time") or notification.end_time or notification.start_time,
                device_icon="🖥️",
                source_area_icon="📈",
                event_icon="✅" if is_recovery else "🚨",
                details=tuple(details),
            )
        )
