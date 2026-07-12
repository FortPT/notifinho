"""
Notifinho

discord_grafana.py

Discord formatter for Grafana Alerting events.
"""

from __future__ import annotations

import re

from datetime import datetime

from formatters.base import BaseFormatter
from models import Notification
from version import VERSION


class GrafanaDiscordFormatter(BaseFormatter):
    """Format Grafana alerts as bounded Discord embeds."""

    EMBED_TEXT_BUDGET = 5900

    KNOWN_METADATA_KEYS = (
        "alert_count",
        "alert_rule",
        "folder",
        "dashboard",
        "panel",
        "organization",
        "datasource",
        "labels",
        "values",
        "dashboard_url",
        "panel_url",
        "silence_url",
        "rule_url",
    )

    LABELS = {
        "alert_count": "🔢 Alert count",
        "alert_rule": "📏 Alert rule",
        "folder": "📁 Folder",
        "dashboard": "📊 Dashboard",
        "panel": "📈 Panel",
        "organization": "🏢 Organization",
        "datasource": "🗄️ Datasource",
        "labels": "🏷️ Labels",
        "values": "🔢 Values",
        "dashboard_url": "🔗 Dashboard link",
        "panel_url": "🔗 Panel link",
        "silence_url": "🔕 Silence link",
        "rule_url": "🔗 Rule link",
    }

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

        embed = {
            "title": self._truncate(
                f"{icon} {alert_name}",
                256,
            ),
            "description": self._truncate(
                f"Grafana • **{status_text}**"
                + (f" • {state}" if state else ""),
                1024,
            ),
            "color": color,
            "fields": [
                {
                    "name": "🚨 Alert message",
                    "value": self._truncate(
                        message,
                        1024,
                    ),
                    "inline": False,
                },
            ],
            "footer": {
                "text": f"FortPT Labs\nNotifinho v{VERSION}",
            },
        }

        self._add_field(
            embed,
            "📌 State",
            state,
            inline=True,
        )

        self._add_field(
            embed,
            "⚠️ Severity",
            severity,
            inline=True,
        )

        if event_time:

            self._add_field(
                embed,
                "🕒 Event time",
                self._format_datetime(
                    event_time,
                ),
                inline=True,
            )

        for key in self.KNOWN_METADATA_KEYS:

            self._add_field(
                embed,
                self.LABELS[key],
                metadata.get(key),
                inline=key not in {
                    "labels",
                    "values",
                },
            )

        for label, value in self._unknown_fields(
            metadata,
        ):

            self._add_field(
                embed,
                f"📌 {label}",
                value,
                inline=True,
            )

        embed["fields"] = embed["fields"][:25]

        self._enforce_embed_budget(
            embed,
        )

        return {
            "embeds": [
                embed,
            ],
        }

    def _add_field(
        self,
        embed: dict,
        name: str,
        value,
        inline: bool,
    ) -> None:

        value_text = self._text(
            value,
        )

        if not value_text:

            return

        embed["fields"].append(
            {
                "name": self._truncate(
                    name,
                    256,
                ),
                "value": self._truncate(
                    value_text,
                    1024,
                ),
                "inline": inline,
            }
        )

    def _status_meta(
        self,
        status: str,
        state: str,
        severity: str,
    ) -> tuple[str, int, str]:

        status_value = self._normalized(
            status,
        )

        state_value = self._normalized(
            state,
        )

        severity_value = self._normalized(
            severity,
        )

        if status_value == "failure":

            return "🚨", 0xE74C3C, "Failure"

        if status_value == "warning":

            return "⚠️", 0xF39C12, "Warning"

        if status_value == "success":

            return "✅", 0x2ECC71, "Resolved"

        if status_value == "information":

            return "ℹ️", 0x3498DB, "Information"

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

            return "🚨", 0xE74C3C, "Failure"

        if combined & {
            "alert",
            "no data",
            "pending",
            "warning",
        }:

            return "⚠️", 0xF39C12, "Warning"

        if combined & {
            "normal",
            "recovered",
            "resolved",
        }:

            return "✅", 0x2ECC71, "Resolved"

        return "ℹ️", 0x3498DB, "Information"

    def _unknown_fields(
        self,
        metadata: dict,
    ) -> list[tuple[str, str]]:

        source_fields = metadata.get(
            "source_fields",
            {},
        )

        if not isinstance(source_fields, dict):

            return []

        ignored = {
            self._normalize_key(alias)
            for aliases in (
                (
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
                ),
            )
            for alias in aliases
        }

        values = []

        for key, raw_value in source_fields.items():

            if self._normalize_key(key) in ignored:

                continue

            value = self._text(
                raw_value,
            )

            if value:

                values.append(
                    (
                        self._label(key),
                        value,
                    )
                )

        return values

    def _enforce_embed_budget(
        self,
        embed: dict,
    ) -> None:

        fields = embed.get(
            "fields",
            [],
        )

        while (
            len(fields) > 1
            and self._embed_text_size(embed) > self.EMBED_TEXT_BUDGET
        ):

            fields.pop()

        if self._embed_text_size(embed) <= self.EMBED_TEXT_BUDGET:

            return

        event = fields[0]
        current = str(
            event.get(
                "value",
                "",
            )
        )

        excess = self._embed_text_size(embed) - self.EMBED_TEXT_BUDGET

        event["value"] = self._truncate(
            current,
            max(
                len(current) - excess,
                1,
            ),
        )

    def _embed_text_size(
        self,
        embed: dict,
    ) -> int:

        size = sum(
            len(
                str(
                    embed.get(key, "")
                )
            )
            for key in (
                "title",
                "description",
            )
        )

        for section, key in (
            (
                "footer",
                "text",
            ),
            (
                "author",
                "name",
            ),
        ):

            value = embed.get(
                section,
                {},
            )

            if isinstance(value, dict):

                size += len(
                    str(
                        value.get(key, "")
                    )
                )

        for field in embed.get(
            "fields",
            [],
        ):

            size += len(
                str(
                    field.get("name", "")
                )
            )

            size += len(
                str(
                    field.get("value", "")
                )
            )

        return size

    def _format_datetime(
        self,
        value: str,
    ) -> str:

        value = str(
            value
            or ""
        ).strip()

        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
        ):

            try:

                return datetime.strptime(
                    value,
                    fmt,
                ).strftime(
                    "%d/%m/%y %H:%M",
                )

            except ValueError:

                continue

        return value

    def _normalized(
        self,
        value,
    ) -> str:

        return re.sub(
            r"\s+",
            " ",
            str(
                value
                or ""
            ).casefold().replace(
                "_",
                " ",
            ).replace(
                "-",
                " ",
            ),
        ).strip()

    def _normalize_key(
        self,
        value,
    ) -> str:

        return re.sub(
            r"[^a-z0-9]",
            "",
            str(
                value
                or ""
            ).casefold(),
        )

    def _label(
        self,
        value,
    ) -> str:

        words = re.sub(
            r"[_-]+",
            " ",
            str(
                value
                or ""
            ).strip(),
        ).split()

        acronyms = {
            "id": "ID",
            "url": "URL",
        }

        return " ".join(
            acronyms.get(
                word.casefold(),
                word.capitalize(),
            )
            for word in words
        )

    def _text(
        self,
        value,
    ) -> str:

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

        return str(
            value,
        ).strip()

    def _truncate(
        self,
        value: str,
        limit: int,
    ) -> str:

        if len(value) <= limit:

            return value

        return value[: limit - 1].rstrip() + "…"
