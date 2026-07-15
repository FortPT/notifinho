"""
Notifinho

teams_zabbix.py

Microsoft Teams Adaptive Card formatter
for Zabbix monitoring events.
"""

from __future__ import annotations

from typing import Any

from config import config
from formatters.base import BaseFormatter
from models import Notification
from version import VERSION


class ZabbixTeamsFormatter(BaseFormatter):
    """
    Format Zabbix problem and recovery notifications
    as Microsoft Teams Adaptive Cards.
    """

    def format(
        self,
        notification: Notification,
    ) -> dict[str, Any]:

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

        if is_recovery:

            icon = "✅"
            accent_color = "Good"
            status_text = "Problem Resolved"
            problem_heading = "Resolved problem"
            problem_icon = "✅"
            severity_heading = "Previous severity"
            time_heading = "Resolved"
            time_icon = "🏁"

        else:

            icon, accent_color = self._severity_meta(
                severity,
            )

            status_text = "Problem"
            problem_heading = "Active problem"
            problem_icon = "🚨"
            severity_heading = "Severity"
            time_heading = "Started"
            time_icon = "🕒"

        body: list[dict[str, Any]] = [
            self._teams_header(
                f"{icon} {host}",
                accent_color,
                "zabbix",
            ),
            {
                "type": "TextBlock",
                "text": f"Zabbix • **{status_text}**",
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
                        "text": f"{problem_icon} {problem_heading}",
                        "weight": "Bolder",
                        "color": accent_color,
                        "wrap": True,
                    },
                    {
                        "type": "TextBlock",
                        "text": problem_name,
                        "weight": "Bolder",
                        "size": "Medium",
                        "spacing": "Small",
                        "wrap": True,
                    },
                ],
            },
        ]

        metric_columns: list[dict[str, Any]] = []

        metric_columns.append(
            self._metric_column(
                icon="⚠️",
                label=severity_heading,
                value=severity,
            )
        )

        if event_time:

            metric_columns.append(
                self._metric_column(
                    icon=time_icon,
                    label=time_heading,
                    value=self._format_datetime(
                        event_time,
                    ),
                )
            )

        if notification.duration:

            metric_columns.append(
                self._metric_column(
                    icon="⏱",
                    label="Duration",
                    value=notification.duration,
                )
            )

        if metric_columns:

            body.append(
                {
                    "type": "ColumnSet",
                    "spacing": "Medium",
                    "columns": metric_columns,
                }
            )

        if operational_data:

            body.append(
                {
                    "type": "Container",
                    "spacing": "Medium",
                    "separator": True,
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": "📊 Operational data",
                            "weight": "Bolder",
                            "wrap": True,
                        },
                        {
                            "type": "TextBlock",
                            "text": str(
                                operational_data,
                            ),
                            "spacing": "Small",
                            "wrap": True,
                        },
                    ],
                }
            )

        show_ids = config.get(
            "notifications",
            "zabbix",
            "show_ids",
            default=False,
        )

        if show_ids and problem_id:

            body.append(
                {
                    "type": "TextBlock",
                    "text": f"Event ID: `{problem_id}`",
                    "isSubtle": True,
                    "size": "Small",
                    "spacing": "Medium",
                    "separator": True,
                    "wrap": True,
                }
            )

        body.append(
            {
                "type": "TextBlock",
                "text": f"FortPT Labs • Notifinho v{VERSION}",
                "isSubtle": True,
                "size": "Small",
                "spacing": "Medium",
                "separator": True,
                "wrap": True,
            }
        )

        card = {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.4",
            "msteams": {
                "width": "Full",
            },
            "body": body,
        }

        return {
            "type": "message",
            "attachments": [
                {
                    "contentType": (
                        "application/vnd.microsoft.card.adaptive"
                    ),
                    "content": card,
                }
            ],
        }

    def _metric_column(
        self,
        icon: str,
        label: str,
        value,
    ) -> dict[str, Any]:

        return {
            "type": "Column",
            "width": "stretch",
            "items": [
                {
                    "type": "TextBlock",
                    "text": f"{icon} {label}",
                    "weight": "Bolder",
                    "size": "Small",
                    "wrap": True,
                },
                {
                    "type": "TextBlock",
                    "text": str(
                        value or "-",
                    ),
                    "spacing": "Small",
                    "wrap": True,
                },
            ],
        }

    def _severity_meta(
        self,
        severity: str,
    ) -> tuple[str, str]:

        normalized = str(
            severity or "",
        ).lower()

        values = {
            "disaster": (
                "🚨",
                "Attention",
            ),
            "high": (
                "🔴",
                "Attention",
            ),
            "average": (
                "🟠",
                "Warning",
            ),
            "warning": (
                "🟡",
                "Warning",
            ),
            "information": (
                "🔵",
                "Accent",
            ),
            "not classified": (
                "⚪",
                "Default",
            ),
        }

        return values.get(
            normalized,
            (
                "🚨",
                "Attention",
            ),
        )

    def _format_datetime(
        self,
        value: str,
    ) -> str:
        return super()._format_datetime(value)
