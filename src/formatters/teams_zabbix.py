"""
Notifinho

teams_zabbix.py

Microsoft Teams Adaptive Card formatter
for Zabbix monitoring events.
"""

from __future__ import annotations

from datetime import datetime
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
            color = "Good"
            status_text = "Problem Resolved"
            problem_label = "Resolved problem"
            severity_label = "Previous severity"
            time_label = "Resolved"

        else:

            icon = self._severity_icon(
                severity,
            )

            color = "Attention"
            status_text = "Problem"
            problem_label = "Problem"
            severity_label = "Severity"
            time_label = "Started"

        body: list[dict[str, Any]] = [
            {
                "type": "TextBlock",
                "text": f"{icon} {host}",
                "weight": "Bolder",
                "size": "Large",
                "color": color,
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": f"Zabbix • **{status_text}**",
                "isSubtle": True,
                "spacing": "Small",
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": f"**{problem_label}**",
                "weight": "Bolder",
                "spacing": "Medium",
                "separator": True,
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": problem_name,
                "spacing": "Small",
                "wrap": True,
            },
        ]

        facts: list[dict[str, str]] = []

        self._add_fact(
            facts,
            severity_label,
            severity,
        )

        if notification.duration:

            self._add_fact(
                facts,
                "Duration",
                notification.duration,
            )

        if event_time:

            self._add_fact(
                facts,
                time_label,
                self._format_datetime(
                    event_time,
                ),
            )

        if operational_data:

            self._add_fact(
                facts,
                "Operational data",
                operational_data,
            )

        show_ids = config.get(
            "notifications",
            "zabbix",
            "show_ids",
            default=False,
        )

        if show_ids and problem_id:

            self._add_fact(
                facts,
                "Problem ID",
                problem_id,
            )

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
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": card,
                }
            ],
        }

    def _severity_icon(
        self,
        severity: str,
    ) -> str:

        icons = {
            "disaster": "🚨",
            "high": "🔴",
            "average": "🟠",
            "warning": "🟡",
            "information": "🔵",
            "not classified": "⚪",
        }

        return icons.get(
            str(severity or "").lower(),
            "🚨",
        )

    def _add_fact(
        self,
        facts: list[dict[str, str]],
        title: str,
        value,
    ) -> None:

        if value is None:

            return

        value = str(
            value,
        ).strip()

        if not value or value == "-":

            return

        facts.append(
            {
                "title": f"{title}:",
                "value": value,
            }
        )

    def _format_datetime(
        self,
        value: str,
    ) -> str:

        if not value:

            return "-"

        value = str(
            value,
        ).strip()

        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y.%m.%d %H:%M:%S",
        ]

        for fmt in formats:

            try:

                parsed = datetime.strptime(
                    value,
                    fmt,
                )

                return parsed.strftime(
                    "%d/%m/%y %H:%M",
                )

            except ValueError:

                continue

        return value
