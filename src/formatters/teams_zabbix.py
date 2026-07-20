"""
Notifinho

teams_zabbix.py

Microsoft Teams Adaptive Card formatter
for Zabbix monitoring events.
"""

from __future__ import annotations

from config import config
from formatters.teams_common import TeamsCardData, TeamsCardFormatter, TeamsFact
from models import Notification


class ZabbixTeamsFormatter(TeamsCardFormatter):
    """
    Format Zabbix problem and recovery notifications
    as Microsoft Teams Adaptive Cards.
    """

    def format(
        self,
        notification: Notification,
    ) -> dict:

        metadata = notification.metadata or {}

        event_type = str(
            metadata.get(
                "event_type",
                "",
            )
        ).lower()

        is_recovery = (
            event_type == "recovery"
            or (notification.status or "").lower()
            in (
                "success",
                "resolved",
                "recovery",
            )
        )

        host = (
            metadata.get("host")
            or "Unknown host"
        )

        problem_name = (
            metadata.get("problem_name")
            or notification.title
            or notification.subject
            or "Zabbix event"
        )

        severity = (
            metadata.get("severity")
            or "Not classified"
        )

        operational_data = metadata.get(
            "operational_data",
            "",
        )

        problem_id = metadata.get(
            "problem_id",
            "",
        )

        event_time = (
            metadata.get("event_time")
            or notification.end_time
            or notification.start_time
        )

        show_ids = config.get(
            "notifications",
            "zabbix",
            "show_ids",
            default=False,
        )

        details = [
            TeamsFact("📊", "Operational data", operational_data),
            TeamsFact("⏱️", "Duration", notification.duration),
        ]
        if show_ids:
            details.append(TeamsFact("🆔", "Event ID", problem_id))
        return self._render_teams_card(
            TeamsCardData(
                source="zabbix",
                integration="Zabbix",
                device=host,
                event=problem_name,
                message=notification.body or problem_name,
                status="success" if is_recovery else notification.status,
                state="problem resolved" if is_recovery else "problem",
                severity=severity,
                category=notification.category or "monitoring",
                source_area=metadata.get("source") or notification.category or "Monitoring",
                event_time=event_time,
                device_icon="🖥️",
                source_area_icon="📈",
                event_icon="✅" if is_recovery else "🚨",
                details=tuple(details),
            )
        )
