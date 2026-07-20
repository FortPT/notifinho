"""Shared Discord embed presentation contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from formatters.base import BaseFormatter
from version import VERSION


@dataclass(frozen=True)
class DiscordFact:
    """One icon-labelled integration-specific Discord field."""

    icon: str
    label: str
    value: Any
    inline: bool = True


@dataclass(frozen=True)
class DiscordCardData:
    """Normalized data consumed by the shared Discord renderer."""

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
    details: tuple[DiscordFact, ...] = ()
    url: str = ""


class DiscordCardFormatter(BaseFormatter):
    """Render normalized integration data using one bounded Discord embed."""

    EMBED_TEXT_BUDGET = 5900
    MAX_FIELDS = 25
    ESSENTIAL_FIELDS = 4

    def _render_discord_card(self, data: DiscordCardData) -> dict[str, Any]:
        status_icon, color, default_state = self._discord_status(
            data.status,
            data.severity,
        )
        state = self._label(data.state) or default_state
        severity = self._label(data.severity) or default_state
        category = self._label(data.category) or "Event"
        source_area = self._label(data.source_area) or category
        device = self._truncate(data.device or data.integration, 120)
        event = self._truncate(data.event or "Notification", 180)
        message = self._truncate(data.message or event, 1024)
        event_time = self._format_datetime(data.event_time) or "—"

        embed: dict[str, Any] = {
            "title": self._truncate(
                f"{data.device_icon} {status_icon} {device} • {event}",
                256,
            ),
            "description": self._truncate(
                f"{data.integration} • {status_icon} **{state}** • "
                f"{data.source_area_icon} {source_area}",
                4096,
            ),
            "color": color,
            "fields": [
                self._discord_field(
                    data.event_icon,
                    "Event",
                    message,
                    inline=False,
                ),
                self._discord_field(status_icon, "Severity", severity),
                self._discord_field(
                    self._category_icon(data.category),
                    "Category",
                    category,
                ),
                self._discord_field("🕒", "Event time", event_time),
            ],
            "footer": {"text": f"FortPT Labs\nNotifinho v{VERSION}"},
        }

        for fact in data.details:
            if not self._meaningful_fact(fact.value):
                continue
            embed["fields"].append(
                self._discord_field(
                    fact.icon,
                    fact.label,
                    fact.value,
                    inline=fact.inline,
                )
            )

        if data.url:
            embed["url"] = self._truncate(data.url, 2000)

        self._set_discord_thumbnail(embed, data.source)
        self._enforce_discord_budget(embed)
        return {"embeds": [embed]}

    def _discord_field(
        self,
        icon: str,
        label: str,
        value: Any,
        inline: bool = True,
    ) -> dict[str, Any]:
        return {
            "name": self._truncate(f"{icon} {label}", 256),
            "value": self._truncate(value, 1024) or "—",
            "inline": inline,
        }

    def _enforce_discord_budget(self, embed: dict[str, Any]) -> None:
        fields = embed.get("fields", [])
        del fields[self.MAX_FIELDS :]

        # Integration-specific fields are ordered by importance. Preserve the
        # event plus the Severity/Category/Event time row and remove optional
        # details from the end first.
        while (
            len(fields) > self.ESSENTIAL_FIELDS
            and self._discord_text_size(embed) > self.EMBED_TEXT_BUDGET
        ):
            fields.pop()

        if self._discord_text_size(embed) <= self.EMBED_TEXT_BUDGET:
            return

        event_field = fields[0]
        excess = self._discord_text_size(embed) - self.EMBED_TEXT_BUDGET
        value = str(event_field.get("value", ""))
        event_field["value"] = self._truncate(
            value,
            max(len(value) - excess, 1),
        )

    @staticmethod
    def _discord_text_size(embed: dict[str, Any]) -> int:
        size = len(str(embed.get("title", "")))
        size += len(str(embed.get("description", "")))
        size += len(str(embed.get("footer", {}).get("text", "")))
        for field in embed.get("fields", []):
            size += len(str(field.get("name", "")))
            size += len(str(field.get("value", "")))
        return size

    # Compatibility for existing formatter limit tests and integrations that
    # inspected the former product-specific helpers.
    def _embed_text_size(self, embed: dict[str, Any]) -> int:
        return self._discord_text_size(embed)

    @staticmethod
    def _discord_status(status: Any, severity: Any = "") -> tuple[str, int, str]:
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

        # Current state wins over historical severity on recovery cards.
        if status_value in resolved:
            return "✅", 0x2ECC71, "Resolved"
        if status_value in critical:
            return "🚨", 0xE74C3C, "Critical"
        if status_value in warning:
            return "⚠️", 0xF39C12, "Warning"
        if severity_value in critical:
            return "🚨", 0xE74C3C, "Critical"
        if severity_value in warning:
            return "⚠️", 0xF39C12, "Warning"
        if severity_value in resolved:
            return "✅", 0x2ECC71, "Resolved"
        return "ℹ️", 0x3498DB, "Information"

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
        if value is None:
            return False
        text = self._sanitize_text(value).strip()
        return text.casefold() not in {"", "-", "—", "n/a", "none", "null"}
