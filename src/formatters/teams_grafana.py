"""
Notifinho

teams_grafana.py

Microsoft Teams Adaptive Card formatter for Grafana alerts.
"""

from __future__ import annotations

import re

from formatters.teams_common import TeamsCardData, TeamsCardFormatter, TeamsFact
from models import Notification


class GrafanaTeamsFormatter(TeamsCardFormatter):
    """Format Grafana alerts as Microsoft Teams Adaptive Cards."""

    def format(
        self,
        notification: Notification,
    ) -> dict:

        metadata = notification.metadata or {}

        state = self._text(
            metadata.get("state")
        )

        severity = self._text(
            metadata.get("severity")
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

        details = []

        for icon, title, key in (
            (
                "📏",
                "Alert rule",
                "alert_rule",
            ),
            (
                "📁",
                "Folder",
                "folder",
            ),
            (
                "📊",
                "Dashboard",
                "dashboard",
            ),
            (
                "🧩",
                "Panel",
                "panel",
            ),
            (
                "🗄️",
                "Datasource",
                "datasource",
            ),
            (
                "🏢",
                "Organization",
                "organization",
            ),
            (
                "🏷️",
                "Labels",
                "labels",
            ),
            (
                "🔢",
                "Values",
                "values",
            ),
        ):
            value = self._text(metadata.get(key))
            if value:
                details.append(TeamsFact(icon, title, value))

        alert_count = self._text(metadata.get("alert_count"))
        if alert_count and alert_count != "0":
            details.append(TeamsFact("🔢", "Alert count", alert_count))

        for title, value in self._unknown_facts(
            metadata,
        ):
            if len(details) >= 20:
                break
            details.append(TeamsFact("📌", title, value))

        actions = []
        for title, key in (
            ("Open dashboard", "dashboard_url"),
            ("Open panel", "panel_url"),
            ("Silence alert", "silence_url"),
            ("Open rule", "rule_url"),
        ):
            url = self._text(metadata.get(key))
            if url:
                actions.append({"type": "Action.OpenUrl", "title": title, "url": url})

        device = self._text(
            metadata.get("instance")
            or metadata.get("host")
            or metadata.get("dashboard")
            or "Grafana"
        )
        return self._render_teams_card(
            TeamsCardData(
                source="grafana",
                integration="Grafana",
                device=device,
                event=alert_name,
                message=message,
                status=notification.status or state,
                state=state or notification.status,
                severity=severity or notification.status,
                category=notification.category or "monitoring",
                source_area=metadata.get("panel") or metadata.get("folder") or "Monitoring",
                event_time=event_time,
                device_icon="📊",
                source_area_icon="📈",
                event_icon="🚨",
                details=tuple(details[:20]),
                actions=tuple(actions),
            )
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
