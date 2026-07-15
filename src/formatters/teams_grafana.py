"""
Notifinho

teams_grafana.py

Microsoft Teams Adaptive Card formatter for Grafana alerts.
"""

from __future__ import annotations

import re

from typing import Any

from formatters.base import BaseFormatter
from models import Notification
from version import VERSION


class GrafanaTeamsFormatter(BaseFormatter):
    """Format Grafana alerts as Microsoft Teams Adaptive Cards."""

    def format(
        self,
        notification: Notification,
    ) -> dict[str, Any]:

        metadata = notification.metadata or {}

        state = self._text(
            metadata.get("state")
        )

        severity = self._text(
            metadata.get("severity")
        )

        icon, color, status_text = self._status_meta(
            notification.status,
            state,
            severity,
        )

        alert_name = self._text(
            metadata.get("alert_name")
            or notification.title
            or notification.subject
            or "Grafana alert"
        )

        message = self._text(
            metadata.get("summary")
            or metadata.get("message")
            or metadata.get("description")
            or notification.body
            or "Grafana notification"
        )

        event_time = self._text(
            metadata.get("event_time")
            or notification.end_time
            or notification.start_time
        )

        body: list[dict[str, Any]] = [
            self._teams_header(
                f"{icon} {alert_name}",
                color,
                "grafana",
            ),
            {
                "type": "TextBlock",
                "text": f"Grafana • **{status_text}**"
                + (f" • {state}" if state else ""),
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
                        "text": "🚨 Grafana alert",
                        "weight": "Bolder",
                        "color": color,
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

        metrics = []

        self._add_metric(
            metrics,
            "📌",
            "State",
            state,
        )

        self._add_metric(
            metrics,
            "⚠️",
            "Severity",
            severity,
        )

        if event_time:

            self._add_metric(
                metrics,
                "🕒",
                "Event time",
                self._format_datetime(
                    event_time,
                ),
            )

        self._add_metric(
            metrics,
            "🔢",
            "Alert count",
            metadata.get("alert_count"),
        )

        if metrics:

            body.append(
                {
                    "type": "ColumnSet",
                    "spacing": "Medium",
                    "columns": metrics,
                }
            )

        facts = []

        for title, key in (
            (
                "Alert rule",
                "alert_rule",
            ),
            (
                "Folder",
                "folder",
            ),
            (
                "Dashboard",
                "dashboard",
            ),
            (
                "Panel",
                "panel",
            ),
            (
                "Datasource",
                "datasource",
            ),
            (
                "Organization",
                "organization",
            ),
            (
                "Labels",
                "labels",
            ),
            (
                "Values",
                "values",
            ),
            (
                "Dashboard link",
                "dashboard_url",
            ),
            (
                "Panel link",
                "panel_url",
            ),
            (
                "Silence link",
                "silence_url",
            ),
            (
                "Rule link",
                "rule_url",
            ),
        ):

            self._add_fact(
                facts,
                title,
                metadata.get(key),
            )

        for title, value in self._unknown_facts(
            metadata,
        ):

            self._add_fact(
                facts,
                title,
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
                            "text": "📋 Alert details",
                            "weight": "Bolder",
                            "wrap": True,
                        },
                        {
                            "type": "FactSet",
                            "spacing": "Small",
                            "facts": facts[:20],
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

    def _status_meta(
        self,
        status: str,
        state: str,
        severity: str,
    ) -> tuple[str, str, str]:

        status_value = self._normalized(status)
        state_value = self._normalized(state)
        severity_value = self._normalized(severity)

        if status_value == "failure":

            return "🚨", "Attention", "Failure"

        if status_value == "warning":

            return "⚠️", "Warning", "Warning"

        if status_value == "success":

            return "✅", "Good", "Resolved"

        if status_value == "information":

            return "ℹ️", "Accent", "Information"

        combined = {
            state_value,
            severity_value,
        }

        if combined & {
            "critical",
            "error",
            "failed",
            "failure",
            "firing",
        }:

            return "🚨", "Attention", "Failure"

        if combined & {
            "alert",
            "no data",
            "pending",
            "warning",
        }:

            return "⚠️", "Warning", "Warning"

        if combined & {
            "normal",
            "recovered",
            "resolved",
        }:

            return "✅", "Good", "Resolved"

        return "ℹ️", "Accent", "Information"

    def _add_metric(
        self,
        metrics: list[dict[str, Any]],
        icon: str,
        label: str,
        value,
    ) -> None:

        value_text = self._text(value)

        if not value_text or value_text == "0":

            return

        metrics.append(
            {
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
                        "text": value_text,
                        "spacing": "Small",
                        "wrap": True,
                    },
                ],
            }
        )

    def _add_fact(
        self,
        facts: list[dict[str, str]],
        title: str,
        value,
    ) -> None:

        value_text = self._text(value)

        if not value_text:

            return

        facts.append(
            {
                "title": f"{title}:",
                "value": value_text,
            }
        )

    def _unknown_facts(
        self,
        metadata: dict,
    ) -> list[tuple[str, str]]:

        source_fields = metadata.get(
            "source_fields",
            {},
        )

        if not isinstance(source_fields, dict):

            return []

        known = {
            self._normalize_key(value)
            for value in (
                "alert name",
                "alert rule",
                "rule name",
                "state",
                "status",
                "severity",
                "folder",
                "grafana folder",
                "dashboard",
                "panel",
                "organization",
                "datasource",
                "data source",
                "labels",
                "values",
                "summary",
                "description",
                "message",
                "starts at",
                "startsat",
                "ends at",
                "endsat",
                "event time",
                "dashboardurl",
                "dashboard url",
                "panelurl",
                "panel url",
                "silenceurl",
                "silence url",
                "ruleurl",
                "rule url",
                "alert count",
            )
        }

        values = []

        for key, raw_value in source_fields.items():

            if self._normalize_key(key) in known:

                continue

            value = self._text(raw_value)

            if value:

                values.append(
                    (
                        self._label(key),
                        value,
                    )
                )

        return values

    def _format_datetime(
        self,
        value: str,
    ) -> str:
        return super()._format_datetime(value)

    def _normalized(self, value) -> str:

        return re.sub(
            r"\s+",
            " ",
            str(value or "").casefold().replace(
                "_",
                " ",
            ).replace(
                "-",
                " ",
            ),
        ).strip()

    def _normalize_key(self, value) -> str:

        return re.sub(
            r"[^a-z0-9]",
            "",
            str(value or "").casefold(),
        )

    def _label(self, value) -> str:

        return " ".join(
            word.capitalize()
            for word in re.sub(
                r"[_-]+",
                " ",
                str(value or "").strip(),
            ).split()
        )

    def _text(self, value) -> str:

        if value is None:

            return ""

        if isinstance(value, dict):

            return ", ".join(
                f"{self._label(key)}: {text}"
                for key, nested in value.items()
                if (text := self._text(nested))
            )

        if isinstance(value, (list, tuple, set)):

            return ", ".join(
                text
                for item in value
                if (text := self._text(item))
            )

        return str(value).strip()
