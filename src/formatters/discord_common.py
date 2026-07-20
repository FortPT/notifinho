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
    SEPARATOR = "────────────────────────────────────────────────────"

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
        event_time = self._format_datetime(data.event_time)

        fields = [
            self._discord_field(
                "",
                "",
                self._discord_highlight(message),
                inline=False,
            ),
            self._discord_field(status_icon, "Severity", severity),
            self._discord_field(
                self._category_icon(data.category),
                "Category",
                category,
            ),
        ]
        if event_time:
            fields.append(
                self._discord_field("🕒", "Event time", event_time)
            )

        embed: dict[str, Any] = {
            "title": self._truncate(
                f"{data.device_icon} {status_icon} {device} • {event}",
                256,
            ),
            "description": self._truncate(
                f"\u200b\n{data.integration} • {status_icon} **{state}** • "
                f"{data.source_area_icon} {source_area}",
                4096,
            ),
            "color": color,
            "fields": fields,
            "footer": {"text": f"FortPT Labs • Notifinho v{VERSION}"},
        }

        detail_fields = self._discord_detail_fields(data.details)
        if detail_fields:
            embed["fields"].extend(detail_fields)

        if data.url:
            embed["url"] = self._truncate(data.url, 2000)

        self._set_discord_thumbnail(embed, data.source)
        self._enforce_discord_budget(embed)
        self._finish_discord_footer(embed)
        return {"embeds": [embed]}

    def _discord_highlight(self, value: Any) -> str:
        """Render the event message as a full-width Discord code block."""

        text = self._truncate(value, 1014).replace("```", "'''")
        return (
            f"```\n{text or '—'}\n```\n\u200b\n{self.SEPARATOR}"
        )

    def _finish_discord_footer(self, embed: dict[str, Any]) -> None:
        """Place one full-width rule immediately above the footer."""

        fields = embed.get("fields", [])
        if not fields:
            return
        last = fields[-1]
        if last.get("value") == self.SEPARATOR:
            self._trim_discord_event_for_footer(embed)
            return
        if last.get("name") in {"📋 Event details", "\u200b"} and not last.get(
            "inline",
            True,
        ):
            value = str(last.get("value") or "").rstrip()
            maximum = 1024 - len(self.SEPARATOR) - 1
            last["value"] = (
                f"{self._truncate(value, maximum).rstrip()}\n{self.SEPARATOR}"
            )
        elif len(fields) < self.MAX_FIELDS:
            fields.append(self._discord_separator())
        self._trim_discord_event_for_footer(embed)

    def _trim_discord_event_for_footer(self, embed: dict[str, Any]) -> None:
        """Keep the mandatory rules without exceeding Discord's text limit."""

        excess = self._discord_text_size(embed) - self.EMBED_TEXT_BUDGET
        if excess <= 0:
            return
        fields = embed.get("fields", [])
        if not fields:
            return
        event = fields[0]
        value = str(event.get("value") or "")
        suffix = f"\n```\n\u200b\n{self.SEPARATOR}"
        if value.endswith(suffix):
            body = value[: -len(suffix)]
            event["value"] = (
                f"{self._truncate(body, max(len(body) - excess, 1))}{suffix}"
            )
            return
        event["value"] = self._truncate(
            value,
            max(len(value) - excess, 1),
        )

    def _discord_detail_fields(
        self,
        details: tuple[DiscordFact, ...],
    ) -> list[dict[str, Any]]:
        """Group integration-specific details into readable vertical lists."""

        entries: list[str] = []
        for fact in details:
            if not self._meaningful_fact(fact.value):
                continue
            label = self._truncate(fact.label, 120)
            value = self._truncate(fact.value, 880)
            if "\n" in value:
                entries.append(f"{fact.icon} **{label}:**\n{value}")
            else:
                entries.append(f"{fact.icon} **{label}:** {value}")

        if not entries:
            return []

        chunks: list[str] = []
        current = ""
        for entry in entries:
            candidate = f"{current}\n{entry}" if current else entry
            if len(candidate) <= 1024:
                current = candidate
                continue
            if current:
                chunks.append(current)
            current = self._truncate(entry, 1024)
        if current:
            chunks.append(current)

        fields = []
        for index, chunk in enumerate(chunks):
            fields.append({
                "name": "📋 Event details" if index == 0 else "\u200b",
                "value": chunk,
                "inline": False,
            })
        return fields

    def _discord_separator(self) -> dict[str, Any]:
        return {
            "name": "\u200b",
            "value": self.SEPARATOR,
            "inline": False,
        }

    def _discord_field(
        self,
        icon: str,
        label: str,
        value: Any,
        inline: bool = True,
    ) -> dict[str, Any]:
        name = f"{icon} {label}".strip() or "\u200b"
        return {
            "name": self._truncate(name, 256),
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
