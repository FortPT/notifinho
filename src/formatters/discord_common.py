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
    ESSENTIAL_FIELDS = 3
    # Discord renders embed content more narrowly when a thumbnail is
    # present. Keep the shared rule inside that narrowest width so it never
    # wraps into a second fragment.
    SEPARATOR = "───────────────────────────────────────────────"

    COMPONENTS_V2_FLAG = 1 << 15
    COMPONENT_TYPE_SECTION = 9
    COMPONENT_TYPE_TEXT_DISPLAY = 10
    COMPONENT_TYPE_THUMBNAIL = 11
    COMPONENT_TYPE_SEPARATOR = 14
    COMPONENT_TYPE_CONTAINER = 17

    def _render_discord_card(self, data: DiscordCardData) -> dict[str, Any]:
        status_icon, color, default_state = self._discord_status(
            data.status,
            data.severity,
        )
        state = self._label(data.state) or default_state
        severity = self._label(data.severity) or default_state
        category = self._label(data.category) or "Event"
        source_area = self._truncate(
            self._label(data.source_area) or category,
            700,
        )
        device = self._truncate(data.device or data.integration, 120)
        event = self._truncate(data.event or "Notification", 180)
        message = self._truncate(data.message or event, 1024)
        event_time = self._format_datetime(data.event_time)

        fields = [
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
                f"{data.integration} • {status_icon} **{state}** • "
                f"{data.source_area_icon} {source_area}\n"
                f"{self.SEPARATOR}\n{self._discord_highlight(message)}",
                2048,
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

    def _render_discord_components_v2(
        self,
        data: DiscordCardData,
    ) -> dict[str, Any]:
        """Render one responsive Discord Components V2 card.

        This is intentionally opt-in while the layout is validated against a
        real webhook on desktop and mobile. Legacy embed formatters continue
        to use :meth:`_render_discord_card`.
        """

        status_icon, color, default_state = self._discord_status(
            data.status,
            data.severity,
        )
        state = self._label(data.state) or default_state
        severity = self._label(data.severity) or default_state
        category = self._label(data.category) or "Event"
        source_area = self._truncate(
            self._label(data.source_area) or category,
            280,
        )
        device = self._truncate(data.device or data.integration, 120)
        event = self._truncate(data.event or "Notification", 180)
        message = self._truncate(data.message or event, 1000)
        event_time = self._format_datetime(data.event_time)

        header_text = (
            f"### {data.device_icon} {status_icon} {device} • {event}\n"
            f"-# {data.integration} • {status_icon} **{state}** • "
            f"{data.source_area_icon} {source_area}"
        )
        icon_url = self._product_icon_url(data.source)
        if icon_url:
            header = {
                "type": self.COMPONENT_TYPE_SECTION,
                "components": [self._discord_v2_text(header_text)],
                "accessory": {
                    "type": self.COMPONENT_TYPE_THUMBNAIL,
                    "media": {"url": icon_url},
                    "description": f"{data.integration} logo",
                },
            }
        else:
            header = self._discord_v2_text(header_text)

        metrics = [
            f"{status_icon} **Severity:** {severity}",
            (
                f"{self._category_icon(data.category)} "
                f"**Category:** {category}"
            ),
        ]
        if event_time:
            metrics.append(f"🕒 **Event time:** {event_time}")

        children = [
            header,
            self._discord_v2_separator(),
            self._discord_v2_text(self._discord_highlight(message)),
            self._discord_v2_separator(divider=False),
            self._discord_v2_text("  •  ".join(metrics)),
        ]

        details = self._discord_v2_details(data.details)
        if details:
            children.extend((
                self._discord_v2_separator(),
                self._discord_v2_text(
                    f"**📋 Event details**\n{details}",
                ),
            ))

        children.extend((
            self._discord_v2_separator(),
            self._discord_v2_text(
                f"-# FortPT Labs • Notifinho v{VERSION}",
            ),
        ))

        return {
            "flags": self.COMPONENTS_V2_FLAG,
            "components": [
                {
                    "type": self.COMPONENT_TYPE_CONTAINER,
                    "accent_color": color,
                    "components": children,
                }
            ],
        }

    def _discord_v2_details(
        self,
        details: tuple[DiscordFact, ...],
    ) -> str:
        """Return a compact, bounded vertical detail list."""

        entries = []
        for fact in details:
            if not self._meaningful_fact(fact.value):
                continue
            label = self._truncate(fact.label, 120)
            value = self._truncate(fact.value, 700)
            entries.append(f"{fact.icon} **{label}:** {value}")
        return self._truncate("\n".join(entries), 1800)

    def _discord_v2_text(self, content: Any) -> dict[str, Any]:
        """Build a Text Display without allowing source text to ping users."""

        safe = self._truncate(content, 2000).replace("@", "@\u200b")
        return {
            "type": self.COMPONENT_TYPE_TEXT_DISPLAY,
            "content": safe or "—",
        }

    def _discord_v2_separator(
        self,
        *,
        divider: bool = True,
    ) -> dict[str, Any]:
        """Build a native divider that follows the rendered card width."""

        return {
            "type": self.COMPONENT_TYPE_SEPARATOR,
            "divider": divider,
            "spacing": 1,
        }

    def _discord_highlight(self, value: Any) -> str:
        """Render the event message as a full-width Discord code block."""

        text = self._truncate(value, 1014).replace("```", "'''")
        return f"```\n{text or '—'}\n```"

    def _finish_discord_footer(self, embed: dict[str, Any]) -> None:
        """Place one full-width rule immediately above the footer."""

        fields = embed.get("fields", [])
        if not fields:
            return
        last = fields[-1]
        if str(last.get("value") or "").endswith(self.SEPARATOR):
            self._trim_discord_description_for_budget(embed)
            return
        if last.get("name") == "\u200b" and not last.get(
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
        self._trim_discord_description_for_budget(embed)

    def _trim_discord_description_for_budget(
        self,
        embed: dict[str, Any],
    ) -> None:
        """Keep the mandatory rules without exceeding Discord's text limit."""

        excess = self._discord_text_size(embed) - self.EMBED_TEXT_BUDGET
        if excess <= 0:
            return
        description = str(embed.get("description") or "")
        marker = f"\n{self.SEPARATOR}\n```\n"
        suffix = "\n```"
        if marker in description and description.endswith(suffix):
            context, message = description.split(marker, 1)
            message = message[: -len(suffix)]
            maximum = max(len(message) - excess, 1)
            embed["description"] = (
                f"{context}{marker}{self._truncate(message, maximum)}{suffix}"
            )
            return
        embed["description"] = self._truncate(
            description,
            max(len(description) - excess, 1),
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
            if len(candidate) <= 880:
                current = candidate
                continue
            if current:
                chunks.append(current)
            current = self._truncate(entry, 880)
        if current:
            chunks.append(current)

        fields = []
        for index, chunk in enumerate(chunks):
            if index == 0:
                chunk = (
                    f"{self.SEPARATOR}\n"
                    f"📋 **Event details**\n{chunk}"
                )
            fields.append({
                "name": "\u200b",
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
        # Severity/Category/Event time row and remove optional details from
        # the end first.
        essential_fields = min(
            self.ESSENTIAL_FIELDS,
            sum(bool(field.get("inline")) for field in fields),
        )
        while (
            len(fields) > essential_fields
            and self._discord_text_size(embed) > self.EMBED_TEXT_BUDGET
        ):
            fields.pop()

        if self._discord_text_size(embed) <= self.EMBED_TEXT_BUDGET:
            return

        excess = self._discord_text_size(embed) - self.EMBED_TEXT_BUDGET
        description = str(embed.get("description", ""))
        embed["description"] = self._truncate(
            description,
            max(len(description) - excess, 1),
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
