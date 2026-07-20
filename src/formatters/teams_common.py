"""Shared Microsoft Teams Adaptive Card presentation contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from formatters.base import BaseFormatter
from version import VERSION


@dataclass(frozen=True)
class TeamsFact:
    """One icon-labelled integration-specific card detail."""

    icon: str
    label: str
    value: Any


@dataclass(frozen=True)
class TeamsCardData:
    """Normalized data consumed by the shared Teams renderer."""

    source: str
    integration: str
    device: str
    event: str
    message: str
    status: str = "information"
    state: str = ""
    severity: str = ""
    category: str = ""
    source_area: str = ""
    event_time: Any = ""
    device_icon: str = "🖥️"
    source_area_icon: str = "📍"
    event_icon: str = "🔔"
    details: tuple[TeamsFact, ...] = ()
    extra_body: tuple[dict[str, Any], ...] = ()
    actions: tuple[dict[str, Any], ...] = ()


class TeamsCardFormatter(BaseFormatter):
    """Render normalized integration data using one Teams card layout."""

    def _render_teams_card(self, data: TeamsCardData) -> dict[str, Any]:
        status_icon, color, default_state = self._teams_status(
            data.status,
            data.severity,
        )
        state = self._label(data.state) or default_state
        severity = self._label(data.severity) or default_state
        category = self._label(data.category) or "Event"
        source_area = self._label(data.source_area) or category
        device = self._truncate(data.device or data.integration, 160)
        event = self._truncate(data.event or "Notification", 280)
        message = self._truncate(data.message or event, 4000)
        event_time = self._format_datetime(data.event_time) or "—"

        body: list[dict[str, Any]] = [
            self._teams_header(
                f"{data.device_icon} {status_icon} {device} • {event}",
                color,
                data.source,
            ),
            {
                "type": "TextBlock",
                "text": (
                    f"{data.integration} • {status_icon} **{state}** • "
                    f"{data.source_area_icon} {source_area}"
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
                        "text": self._truncate(
                            f"{data.event_icon} {message}",
                            4000,
                        ),
                        "weight": "Bolder",
                        "size": "Medium",
                        "wrap": True,
                    }
                ],
            },
            {
                "type": "ColumnSet",
                "spacing": "Medium",
                "columns": [
                    self._teams_metric(status_icon, "Severity", severity),
                    self._teams_metric(
                        self._category_icon(data.category),
                        "Category",
                        category,
                    ),
                    self._teams_metric("🕒", "Event time", event_time),
                ],
            },
        ]

        facts = [
            {
                "title": f"{fact.icon} {self._truncate(fact.label, 120)}:",
                "value": self._truncate(fact.value, 1000),
            }
            for fact in data.details
            if self._meaningful_fact(fact.value)
        ]
        if facts:
            body.append(
                {
                    "type": "Container",
                    "spacing": "Medium",
                    "separator": True,
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": "🧾 Event details",
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

        body.extend(data.extra_body)
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

        card: dict[str, Any] = {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.4",
            "msteams": {"width": "Full"},
            "body": body,
        }
        if data.actions:
            card["actions"] = list(data.actions)
        return {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": card,
                }
            ],
        }

    @staticmethod
    def _teams_metric(icon: str, label: str, value: Any) -> dict[str, Any]:
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
                    "text": str(value),
                    "spacing": "Small",
                    "wrap": True,
                },
            ],
        }

    @staticmethod
    def _teams_status(status: Any, severity: Any = "") -> tuple[str, str, str]:
        status_value = str(status or "").strip().casefold()
        severity_value = str(severity or "").strip().casefold()
        resolved = {
            "cleared", "normal", "ok", "recovered", "resolved", "success",
            "successful",
        }
        critical = {
            "critical", "danger", "disaster", "emergency", "error",
            "failed", "failure", "high",
        }
        warning = {
            "alert", "average", "caution", "degraded", "medium", "warn",
            "warning",
        }

        # The current event state wins over a historical severity. A recovery
        # from a disaster is green, while an informational event carrying a
        # critical severity remains red.
        if status_value in resolved:
            return "✅", "Good", "Resolved"
        if status_value in critical:
            return "🚨", "Attention", "Critical"
        if status_value in warning:
            return "⚠️", "Warning", "Warning"
        values = {severity_value}
        if values & critical:
            return "🚨", "Attention", "Critical"
        if values & warning:
            return "⚠️", "Warning", "Warning"
        if values & resolved:
            return "✅", "Good", "Resolved"
        return "ℹ️", "Accent", "Information"

    @staticmethod
    def _category_icon(category: Any) -> str:
        value = str(category or "").strip().casefold()
        rules = (
            (("storage", "disk", "raid", "volume"), "💾"),
            (("security", "auth", "login"), "🛡️"),
            (("backup", "replication", "sync"), "🔄"),
            (("power", "ups", "battery"), "🔌"),
            (("network", "wifi", "ethernet"), "🌐"),
            (("update", "firmware"), "⬆️"),
            (("thermal", "temperature", "fan"), "🌡️"),
            (("memory", "dimm", "ecc"), "🧠"),
            (("system", "hardware"), "⚙️"),
        )
        for terms, icon in rules:
            if any(term in value for term in terms):
                return icon
        return "📁"

    @staticmethod
    def _label(value: Any) -> str:
        text = str(value or "").replace("_", " ").strip()
        if not text:
            return ""

        def label_token(token: str) -> str:
            parts = token.split("-")
            return "-".join(
                part
                if part.isupper() or any(character.isdigit() for character in part)
                else part.capitalize()
                for part in parts
            )

        return " ".join(label_token(token) for token in text.split())

    def _meaningful_fact(self, value: Any) -> bool:
        """Reject empty and formatter-sentinel values without hiding zero."""

        if value is None:
            return False
        text = self._sanitize_text(value).strip()
        return text.casefold() not in {"", "-", "—", "n/a", "none", "null"}
