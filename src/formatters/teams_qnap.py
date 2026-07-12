"""
Notifinho

teams_qnap.py

Microsoft Teams Adaptive Card formatter for QNAP events.
"""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from formatters.base import BaseFormatter
from models import Notification
from version import VERSION


class QNAPTeamsFormatter(BaseFormatter):
    """Format QNAP events as Microsoft Teams Adaptive Cards."""

    CATEGORY_ICONS = {
        "storage": "💾",
        "security": "🔐",
        "backup": "🔄",
        "system": "⚙️",
        "power": "🔌",
        "generic": "🔔",
    }

    OPERATIONAL_KEYS = (
        "event_type",
        "storage_pool",
        "pool",
        "volume",
        "raid_group",
        "raid_level",
        "disk",
        "disk_name",
        "drive",
        "drive_bay",
        "smart_status",
        "backup_job",
        "job_name",
        "task",
        "destination",
        "repository",
        "ups_status",
        "battery_level",
        "battery_capacity",
        "runtime_remaining",
        "power_source",
        "user",
        "username",
        "account",
        "source_ip",
        "ip_address",
        "protocol",
        "firmware_version",
        "current_version",
        "new_version",
    )

    def format(
        self,
        notification: Notification,
    ) -> dict[str, Any]:

        metadata = notification.metadata or {}

        nas_name = self._text(
            metadata.get("nas_name")
            or metadata.get("host")
            or "QNAP NAS"
        )

        category_value = (
            metadata.get("category")
            or notification.category
            or "generic"
        )

        category_key = str(
            category_value,
        ).strip().lower()

        category = self._label(
            category_value,
        )

        category_icon = self.CATEGORY_ICONS.get(
            category_key,
            self.CATEGORY_ICONS["generic"],
        )

        severity = self._text(
            metadata.get("severity"),
        )

        icon, accent_color, status_text = self._status_meta(
            notification.status,
            severity,
        )

        message = self._text(
            metadata.get("message")
            or notification.body
            or notification.title
            or notification.subject
            or "QNAP notification"
        )

        application = self._text(
            metadata.get("application"),
        )

        event_time = self._text(
            metadata.get("event_time")
            or notification.start_time
            or notification.end_time
        )

        body: list[dict[str, Any]] = [
            {
                "type": "TextBlock",
                "text": f"{icon} {nas_name}",
                "weight": "Bolder",
                "size": "Large",
                "color": accent_color,
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": (
                    f"QNAP • **{status_text}** • "
                    f"{category_icon} {category}"
                ),
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
                        "text": f"{category_icon} QNAP event",
                        "weight": "Bolder",
                        "color": accent_color,
                        "wrap": True,
                    },
                    {
                        "type": "TextBlock",
                        "text": message,
                        "weight": "Bolder",
                        "size": "Medium",
                        "spacing": "Small",
                        "wrap": True,
                    },
                ],
            },
        ]

        metric_columns: list[dict[str, Any]] = []

        if severity:

            metric_columns.append(
                self._metric_column(
                    icon="⚠️",
                    label="Severity",
                    value=severity,
                )
            )

        metric_columns.append(
            self._metric_column(
                icon="🗂️",
                label="Category",
                value=category,
            )
        )

        if event_time:

            metric_columns.append(
                self._metric_column(
                    icon="🕒",
                    label="Event time",
                    value=self._format_datetime(
                        event_time,
                    ),
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

        facts: list[dict[str, str]] = []

        self._add_fact(
            facts,
            "Application",
            application,
        )

        for label, value in self._operational_fields(
            metadata,
        )[:15]:

            self._add_fact(
                facts,
                label,
                value,
            )

        if facts:

            body.append(
                {
                    "type": "Container",
                    "spacing": "Medium",
                    "separator": True,
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": "📋 Operational details",
                            "weight": "Bolder",
                            "wrap": True,
                        },
                        {
                            "type": "FactSet",
                            "spacing": "Small",
                            "facts": facts,
                        },
                    ],
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
                        value,
                    ),
                    "spacing": "Small",
                    "wrap": True,
                },
            ],
        }

    def _status_meta(
        self,
        status: str,
        severity: str,
    ) -> tuple[str, str, str]:

        status_value = str(
            status or "",
        ).strip().lower()

        severity_value = str(
            severity or "",
        ).strip().lower()

        failure_values = {
            "critical",
            "danger",
            "disaster",
            "emergency",
            "error",
            "failed",
            "failure",
            "high",
        }

        warning_values = {
            "alert",
            "average",
            "degraded",
            "medium",
            "warn",
            "warning",
        }

        success_values = {
            "normal",
            "ok",
            "recovered",
            "resolved",
            "success",
            "successful",
        }

        information_values = {
            "information",
            "informational",
            "info",
            "notice",
        }

        if status_value in failure_values:

            return "🚨", "Attention", "Failure"

        if status_value in warning_values:

            return "⚠️", "Warning", "Warning"

        if status_value in success_values:

            return "✅", "Good", "Success"

        if status_value in information_values:

            return "ℹ️", "Accent", "Information"

        if severity_value in failure_values:

            return "🚨", "Attention", "Failure"

        if severity_value in warning_values:

            return "⚠️", "Warning", "Warning"

        if severity_value in success_values:

            return "✅", "Good", "Success"

        if severity_value in information_values | {"low"}:

            return "ℹ️", "Accent", "Information"

        return "🔔", "Default", self._label(status_value or "information")

    def _add_fact(
        self,
        facts: list[dict[str, str]],
        title: str,
        value,
    ) -> None:

        value = self._text(
            value,
        )

        if not value:

            return

        facts.append(
            {
                "title": f"{title}:",
                "value": value,
            }
        )

    def _operational_fields(
        self,
        metadata: dict,
    ) -> list[tuple[str, str]]:

        values: list[tuple[str, str]] = []
        seen: set[str] = set()

        for key in self.OPERATIONAL_KEYS:

            value = self._text(
                metadata.get(key),
            )

            if value:

                values.append(
                    (
                        self._label(key),
                        value,
                    )
                )

                seen.add(
                    self._normalize_key(key),
                )

        source_fields = metadata.get(
            "source_fields",
            {},
        )

        if not isinstance(source_fields, dict):

            return values

        ignored = {
            "app",
            "applicationname",
            "application",
            "appname",
            "category",
            "content",
            "date",
            "dateandtime",
            "datetime",
            "description",
            "detail",
            "details",
            "eventcategory",
            "eventmessage",
            "eventtime",
            "host",
            "message",
            "nasname",
            "notificationcategory",
            "severity",
            "sourcefields",
            "subject",
            "time",
            "timestamp",
        }

        for key, raw_value in source_fields.items():

            normalized_key = self._normalize_key(
                key,
            )

            if normalized_key in ignored or normalized_key in seen:

                continue

            value = self._text(
                raw_value,
            )

            if not value:

                continue

            values.append(
                (
                    self._label(key),
                    value,
                )
            )

            seen.add(
                normalized_key,
            )

        return values

    def _normalize_key(
        self,
        value,
    ) -> str:

        return re.sub(
            r"[^a-z0-9]",
            "",
            str(value or "").lower(),
        )

    def _label(
        self,
        value,
    ) -> str:

        words = re.sub(
            r"[_-]+",
            " ",
            str(value or "").strip(),
        ).split()

        acronyms = {
            "hbs": "HBS",
            "hdd": "HDD",
            "id": "ID",
            "ip": "IP",
            "nas": "NAS",
            "qnap": "QNAP",
            "qts": "QTS",
            "raid": "RAID",
            "smart": "SMART",
            "ssd": "SSD",
            "ups": "UPS",
            "usb": "USB",
        }

        return " ".join(
            acronyms.get(
                word.lower(),
                word.capitalize(),
            )
            for word in words
        ) or "Generic"

    def _text(
        self,
        value,
    ) -> str:

        if value is None:

            return ""

        if isinstance(value, dict):

            parts = []

            for key, nested_value in value.items():

                nested_text = self._text(
                    nested_value,
                )

                if nested_text:

                    parts.append(
                        f"{self._label(key)}: {nested_text}"
                    )

            return ", ".join(
                parts,
            )

        if isinstance(value, (list, tuple, set)):

            return ", ".join(
                text
                for item in value
                if (text := self._text(item))
            )

        return str(
            value,
        ).strip()

    def _format_datetime(
        self,
        value: str,
    ) -> str:

        value = str(
            value or "",
        ).strip()

        if not value:

            return "-"

        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
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


# Alternative capitalization for callers following normal PascalCase rules.
QnapTeamsFormatter = QNAPTeamsFormatter
