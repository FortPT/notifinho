"""
Notifinho

discord_qnap.py

Discord formatter for QNAP Notification Center events.
"""

from __future__ import annotations

import re

from formatters.base import BaseFormatter
from models import Notification
from version import VERSION


class QNAPDiscordFormatter(BaseFormatter):
    """Format QNAP events as Discord embeds."""

    EMBED_TEXT_BUDGET = 5900

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
    ) -> dict:

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

        icon, color, status_text = self._status_meta(
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

        embed = {
            "title": self._truncate(
                f"{icon} {nas_name}",
                256,
            ),
            "description": self._truncate(
                (
                    f"QNAP • **{status_text}** • "
                    f"{category_icon} {category}"
                ),
                1024,
            ),
            "color": color,
            "fields": [
                {
                    "name": f"{category_icon} Event",
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

        if severity:

            embed["fields"].append(
                {
                    "name": "⚠️ Severity",
                    "value": self._truncate(
                        severity,
                        1024,
                    ),
                    "inline": True,
                }
            )

        embed["fields"].append(
            {
                "name": "🗂️ Category",
                "value": self._truncate(
                    category,
                    1024,
                ),
                "inline": True,
            }
        )

        if event_time:

            embed["fields"].append(
                {
                    "name": "🕒 Event time",
                    "value": self._truncate(
                        self._format_datetime(
                            event_time,
                        ),
                        1024,
                    ),
                    "inline": True,
                }
            )

        if application:

            embed["fields"].append(
                {
                    "name": "⚙️ Application",
                    "value": self._truncate(
                        application,
                        1024,
                    ),
                    "inline": True,
                }
            )

        for label, value in self._operational_fields(
            metadata,
        )[:15]:

            embed["fields"].append(
                {
                    "name": self._truncate(
                        f"{self._field_icon(label)} {label}",
                        256,
                    ),
                    "value": self._truncate(
                        value,
                        1024,
                    ),
                    "inline": True,
                }
            )

        self._enforce_embed_budget(
            embed,
        )

        self._set_discord_thumbnail(embed, "qnap")

        return {
            "embeds": [
                embed,
            ],
        }

    def _status_meta(
        self,
        status: str,
        severity: str,
    ) -> tuple[str, int, str]:

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

            return "🚨", 0xE74C3C, "Failure"

        if status_value in warning_values:

            return "⚠️", 0xF39C12, "Warning"

        if status_value in success_values:

            return "✅", 0x2ECC71, "Success"

        if status_value in information_values:

            return "ℹ️", 0x3498DB, "Information"

        if severity_value in failure_values:

            return "🚨", 0xE74C3C, "Failure"

        if severity_value in warning_values:

            return "⚠️", 0xF39C12, "Warning"

        if severity_value in success_values:

            return "✅", 0x2ECC71, "Success"

        if severity_value in information_values | {"low"}:

            return "ℹ️", 0x3498DB, "Information"

        return "🔔", 0x95A5A6, self._label(status_value or "information")

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

    def _field_icon(
        self,
        label: str,
    ) -> str:

        normalized = label.lower()

        if "raid" in normalized:

            return "🧱"

        if any(
            value in normalized
            for value in (
                "disk",
                "drive",
                "smart",
            )
        ):

            return "💿"

        if any(
            value in normalized
            for value in (
                "storage",
                "pool",
                "volume",
            )
        ):

            return "💾"

        if any(
            value in normalized
            for value in (
                "backup",
                "destination",
                "hbs",
                "job",
                "repository",
                "task",
            )
        ):

            return "🔄"

        if any(
            value in normalized
            for value in (
                "battery",
                "power",
                "runtime",
                "ups",
            )
        ):

            return "🔌"

        if any(
            value in normalized
            for value in (
                "account",
                "ip",
                "login",
                "protocol",
                "security",
                "user",
            )
        ):

            return "🔐"

        return "📌"

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

    def _truncate(
        self,
        value: str,
        limit: int,
    ) -> str:
        return super()._truncate(value, limit)

    def _enforce_embed_budget(
        self,
        embed: dict,
    ) -> None:
        """Keep the complete Discord embed below its text limit.

        Fields are ordered by importance. Removing from the end therefore
        drops unknown metadata first, then optional operational details,
        while preserving the primary event and status context.
        """

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

        # The first field is the essential event message. It is already
        # individually bounded, but shrink it further as a final safeguard.
        event_field = fields[0]
        excess = (
            self._embed_text_size(embed)
            - self.EMBED_TEXT_BUDGET
        )

        current_value = str(
            event_field.get(
                "value",
                "",
            )
        )

        event_field["value"] = self._truncate(
            current_value,
            max(
                len(current_value) - excess,
                1,
            ),
        )

    def _embed_text_size(
        self,
        embed: dict,
    ) -> int:

        size = len(
            str(
                embed.get(
                    "title",
                    "",
                )
            )
        )

        size += len(
            str(
                embed.get(
                    "description",
                    "",
                )
            )
        )

        footer = embed.get(
            "footer",
            {},
        )

        if isinstance(footer, dict):

            size += len(
                str(
                    footer.get(
                        "text",
                        "",
                    )
                )
            )

        author = embed.get(
            "author",
            {},
        )

        if isinstance(author, dict):

            size += len(
                str(
                    author.get(
                        "name",
                        "",
                    )
                )
            )

        for field in embed.get(
            "fields",
            [],
        ):

            size += len(
                str(
                    field.get(
                        "name",
                        "",
                    )
                )
            )

            size += len(
                str(
                    field.get(
                        "value",
                        "",
                    )
                )
            )

        return size

    def _format_datetime(
        self,
        value: str,
    ) -> str:
        return super()._format_datetime(value)


# Alternative capitalization for callers following normal PascalCase rules.
QnapDiscordFormatter = QNAPDiscordFormatter
