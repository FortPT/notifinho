"""
Notifinho

discord_zabbix.py

Discord formatter for Zabbix monitoring events.
"""

from __future__ import annotations

from config import config
from formatters.base import BaseFormatter
from models import Notification
from version import VERSION


class ZabbixDiscordFormatter(BaseFormatter):
    """
    Format Zabbix problem and recovery notifications
    as Discord embeds.
    """

    SEVERITY_COLORS = {
        "disaster": 0xE74C3C,
        "high": 0xE67E22,
        "average": 0xF1C40F,
        "warning": 0xF39C12,
        "information": 0x3498DB,
        "not classified": 0x95A5A6,
    }

    SEVERITY_ICONS = {
        "disaster": "🚨",
        "high": "🔴",
        "average": "🟠",
        "warning": "🟡",
        "information": "🔵",
        "not classified": "⚪",
    }

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
            or notification.status.lower()
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

        severity_normalized = severity.lower()

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

        if is_recovery:

            icon = "✅"
            color = 0x2ECC71
            status_text = "Problem Resolved"
            problem_label = "✅ Resolved problem"
            severity_label = "⚠️ Previous severity"
            time_label = "🏁 Resolved"

        else:

            icon = self.SEVERITY_ICONS.get(
                severity_normalized,
                "🚨",
            )

            color = self.SEVERITY_COLORS.get(
                severity_normalized,
                0xE74C3C,
            )

            status_text = "Problem"
            problem_label = "🚨 Problem"
            severity_label = "⚠️ Severity"
            time_label = "🕒 Started"

        embed = {
            "title": f"{icon} {host}",
            "description": f"Zabbix • **{status_text}**",
            "color": color,
            "fields": [],
            "footer": {
                "text": f"FortPT Labs\nNotifinho v{VERSION}",
            },
        }

        embed["fields"].append(
            {
                "name": problem_label,
                "value": problem_name,
                "inline": False,
            }
        )

        embed["fields"].append(
            {
                "name": severity_label,
                "value": severity,
                "inline": True,
            }
        )

        if notification.duration:

            embed["fields"].append(
                {
                    "name": "⏱ Duration",
                    "value": notification.duration,
                    "inline": True,
                }
            )

        if event_time:

            embed["fields"].append(
                {
                    "name": time_label,
                    "value": self._format_datetime(
                        event_time,
                    ),
                    "inline": True,
                }
            )

        if operational_data:

            embed["fields"].append(
                {
                    "name": "📊 Operational data",
                    "value": operational_data,
                    "inline": False,
                }
            )

        show_ids = config.get(
            "notifications",
            "zabbix",
            "show_ids",
            default=False,
        )

        if show_ids and problem_id:

            embed["fields"].append(
                {
                    "name": "Problem ID",
                    "value": str(problem_id),
                    "inline": False,
                }
            )

        self._set_discord_thumbnail(embed, "zabbix")

        return {
            "embeds": [
                embed,
            ],
        }

    def _format_datetime(
        self,
        value: str,
    ) -> str:
        return super()._format_datetime(value)
