"""
Notifinho

qnap.py

Provisional parser for QNAP QTS and QuTS hero email
notifications.
"""

from __future__ import annotations

import html
import re

from datetime import datetime
from email.message import EmailMessage

from bs4 import BeautifulSoup

from logger import log
from models import Notification


class Parser:
    """
    Parse QNAP Notification Center email messages.

    The supported formats are based on synthetic fixtures and
    intentionally tolerate missing or unfamiliar source fields.
    """

    FIELD_ALIASES = {
        "application": (
            "application",
            "application name",
            "app",
            "app name",
            "service",
            "source application",
        ),
        "category": (
            "category",
            "event category",
            "notification category",
        ),
        "event_time": (
            "event time",
            "date/time",
            "date and time",
            "datetime",
            "timestamp",
            "time",
            "date",
        ),
        "event_type": (
            "event type",
            "notification type",
            "event",
            "action",
        ),
        "message": (
            "message",
            "event message",
            "description",
            "details",
            "detail",
            "content",
        ),
        "nas_name": (
            "nas name",
            "device name",
            "server name",
            "system name",
            "host name",
            "hostname",
            "host",
        ),
        "severity": (
            "severity",
            "level",
            "priority",
        ),
        "title": (
            "title",
            "event title",
            "notification title",
        ),
    }

    CATEGORY_KEYWORDS = {
        "power": (
            "ups",
            "battery",
            "ac power",
            "mains power",
            "power outage",
            "power failure",
            "power restored",
            "power supply",
        ),
        "security": (
            "security",
            "failed login",
            "login failure",
            "login attempt",
            "logon failure",
            "authentication",
            "unauthorized",
            "brute force",
            "access protection",
            "blocked ip",
            "malware",
            "antivirus",
            "qulog center",
        ),
        "backup": (
            "backup",
            "restore",
            "replication",
            "sync job",
            "synchronization job",
            "hybrid backup sync",
            "hbs 3",
            "hbs",
        ),
        "storage": (
            "storage",
            "storage pool",
            "storage & snapshots",
            "raid",
            "s.m.a.r.t",
            "smart warning",
            "smart error",
            "disk warning",
            "disk error",
            "drive warning",
            "drive error",
            "bad block",
            "volume",
            "ssd cache",
            "snapshot",
        ),
        "system": (
            "system",
            "firmware",
            "software update",
            "application update",
            "update available",
            "app center",
            "notification center",
            "test message",
            "test notification",
            "service stopped",
            "service started",
            "temperature",
            "fan failure",
            "network interface",
        ),
    }

    def parse(
        self,
        message: EmailMessage,
    ) -> Notification:

        notification = Notification()

        notification.source = "qnap"
        notification.category = "generic"
        notification.status = "information"

        self._parse_headers(
            notification,
            message,
        )

        notification.title = (
            notification.subject
            or "QNAP notification"
        )

        notification.metadata = self._empty_metadata()

        try:

            plain_parts, html_parts = self._extract_parts(
                message,
            )

            html_texts = [
                self._plain_text(content)
                for content in html_parts
                if content
            ]

            notification.body = self._clean_body(
                "\n\n".join(
                    plain_parts
                    or html_texts
                )
            )

            source_fields: dict[str, str] = {}

            for content in html_parts:

                self._merge_fields(
                    source_fields,
                    self._parse_html_fields(
                        content,
                    ),
                )

            for content in plain_parts + html_texts:

                self._merge_fields(
                    source_fields,
                    self._parse_plain_fields(
                        content,
                    ),
                )

            fixture_format = self._fixture_format(
                plain_parts,
                html_parts,
            )

            self._populate_notification(
                notification,
                source_fields,
                fixture_format,
            )

        except Exception:

            # A partially supported or malformed QNAP message should
            # still be routed as a useful generic QNAP notification.
            log.exception(
                "Failed to fully parse QNAP email"
            )

        self._log_summary(
            notification,
        )

        return notification

    def _parse_headers(
        self,
        notification: Notification,
        message: EmailMessage,
    ) -> None:

        notification.sender = self._header(
            message,
            "From",
        )

        notification.subject = self._header(
            message,
            "Subject",
        )

    def _header(
        self,
        message: EmailMessage,
        name: str,
    ) -> str:

        try:

            return str(
                message.get(
                    name,
                    "",
                )
                or ""
            ).strip()

        except Exception:

            return ""

    def _extract_parts(
        self,
        message: EmailMessage,
    ) -> tuple[list[str], list[str]]:

        plain_parts: list[str] = []
        html_parts: list[str] = []

        try:

            parts = (
                list(message.walk())
                if message.is_multipart()
                else [message]
            )

        except Exception:

            parts = [message]

        for part in parts:

            try:

                content_type = str(
                    part.get_content_type()
                    or ""
                ).lower()

                disposition = (
                    part.get_content_disposition()
                    or ""
                ).lower()

            except Exception:

                continue

            if disposition == "attachment":

                continue

            if content_type not in {
                "text/plain",
                "text/html",
            }:

                continue

            content = self._decode_part(
                part,
            )

            if not content.strip():

                continue

            if content_type == "text/html":

                html_parts.append(
                    content,
                )

            else:

                plain_parts.append(
                    content,
                )

        if plain_parts or html_parts:

            return plain_parts, html_parts

        # Fall back to the raw payload for malformed messages that do
        # not advertise a usable text content type.
        fallback = self._decode_part(
            message,
        )

        if fallback.strip():

            plain_parts.append(
                fallback,
            )

        return plain_parts, html_parts

    def _decode_part(
        self,
        part,
    ) -> str:

        try:

            content = part.get_content()

        except Exception:

            try:

                content = part.get_payload(
                    decode=True,
                )

            except Exception:

                try:

                    content = part.get_payload()

                except Exception:

                    return ""

        if isinstance(content, bytes):

            try:

                charset = (
                    part.get_content_charset()
                    or "utf-8"
                )

            except Exception:

                charset = "utf-8"

            try:

                return content.decode(
                    charset,
                    errors="replace",
                )

            except LookupError:

                return content.decode(
                    "utf-8",
                    errors="replace",
                )

        if isinstance(content, str):

            return content

        return ""

    def _plain_text(
        self,
        content: str,
    ) -> str:

        if not content:

            return ""

        try:

            soup = BeautifulSoup(
                content,
                "lxml",
            )

            for element in soup.find_all(
                [
                    "script",
                    "style",
                ]
            ):

                element.decompose()

            text = soup.get_text(
                "\n",
                strip=True,
            )

        except Exception:

            text = re.sub(
                r"<[^>]+>",
                " ",
                content,
            )

        return self._clean_body(
            html.unescape(
                text,
            )
        )

    def _clean_body(
        self,
        content: str,
    ) -> str:

        lines = []

        for line in str(
            content
            or ""
        ).splitlines():

            line = re.sub(
                r"\s+",
                " ",
                line,
            ).strip()

            if line:

                lines.append(
                    line,
                )

        return "\n".join(
            lines,
        )

    def _parse_plain_fields(
        self,
        content: str,
    ) -> dict[str, str]:

        fields: dict[str, str] = {}
        current_label = ""

        for raw_line in str(
            content
            or ""
        ).splitlines():

            line = re.sub(
                r"\s+",
                " ",
                raw_line,
            ).strip()

            if not line:

                current_label = ""

                continue

            match = re.match(
                r"^([^:=]{1,80})\s*[:=]\s*(.*)$",
                line,
            )

            if match:

                label = self._normalize_label(
                    match.group(1),
                )

                if self._looks_like_label(
                    label,
                ):

                    value = self._clean_value(
                        match.group(2),
                    )

                    fields[label] = value
                    current_label = label

                    continue

            if (
                current_label
                and (
                    not fields.get(current_label)
                    or current_label in {
                        "content",
                        "description",
                        "detail",
                        "details",
                        "event message",
                        "message",
                    }
                )
            ):

                fields[current_label] = self._append_value(
                    fields.get(
                        current_label,
                        "",
                    ),
                    line,
                )

        return {
            label: value
            for label, value in fields.items()
            if label and value
        }

    def _parse_html_fields(
        self,
        content: str,
    ) -> dict[str, str]:

        if not content:

            return {}

        try:

            soup = BeautifulSoup(
                content,
                "lxml",
            )

        except Exception:

            return {}

        fields: dict[str, str] = {}

        for row in soup.find_all("tr"):

            cells = row.find_all(
                [
                    "th",
                    "td",
                ],
                recursive=False,
            )

            if len(cells) < 2:

                cells = row.find_all(
                    [
                        "th",
                        "td",
                    ]
                )

            if len(cells) < 2:

                continue

            self._store_field(
                fields,
                cells[0].get_text(
                    " ",
                    strip=True,
                ),
                " ".join(
                    cell.get_text(
                        " ",
                        strip=True,
                    )
                    for cell in cells[1:]
                ),
            )

        for term in soup.find_all("dt"):

            description = term.find_next_sibling(
                "dd",
            )

            if description is None:

                continue

            self._store_field(
                fields,
                term.get_text(
                    " ",
                    strip=True,
                ),
                description.get_text(
                    " ",
                    strip=True,
                ),
            )

        for label_node in soup.find_all(
            [
                "b",
                "strong",
            ]
        ):

            value_parts = []

            for sibling in label_node.next_siblings:

                sibling_name = getattr(
                    sibling,
                    "name",
                    None,
                )

                if sibling_name == "br":

                    break

                if sibling_name:

                    value = sibling.get_text(
                        " ",
                        strip=True,
                    )

                else:

                    value = str(
                        sibling,
                    ).strip()

                if value:

                    value_parts.append(
                        value,
                    )

            self._store_field(
                fields,
                label_node.get_text(
                    " ",
                    strip=True,
                ),
                " ".join(
                    value_parts,
                ),
            )

        return fields

    def _store_field(
        self,
        fields: dict[str, str],
        raw_label: str,
        raw_value: str,
    ) -> None:

        label = self._normalize_label(
            raw_label,
        )

        value = self._clean_value(
            raw_value,
        )

        if (
            not self._looks_like_label(label)
            or not value
        ):

            return

        if not fields.get(label):

            fields[label] = value

    def _merge_fields(
        self,
        target: dict[str, str],
        source: dict[str, str],
    ) -> None:

        for label, value in source.items():

            if value and not target.get(label):

                target[label] = value

    def _normalize_label(
        self,
        value: str,
    ) -> str:

        value = html.unescape(
            str(
                value
                or ""
            )
        )

        value = value.replace(
            "\xa0",
            " ",
        ).strip()

        value = value.strip(
            "[]",
        ).rstrip(
            ":",
        )

        return re.sub(
            r"\s+",
            " ",
            value,
        ).strip().casefold()

    def _looks_like_label(
        self,
        label: str,
    ) -> bool:

        if not label or len(label) > 80:

            return False

        if label in {
            "http",
            "https",
        }:

            return False

        return bool(
            re.fullmatch(
                r"[\w][\w\s/&().+#-]*",
                label,
            )
        )

    def _clean_value(
        self,
        value: str,
    ) -> str:

        return re.sub(
            r"\s+",
            " ",
            html.unescape(
                str(
                    value
                    or ""
                )
            ).replace(
                "\xa0",
                " ",
            ),
        ).strip()

    def _append_value(
        self,
        current: str,
        value: str,
    ) -> str:

        if not current:

            return value

        if value in current:

            return current

        return f"{current} {value}"

    def _populate_notification(
        self,
        notification: Notification,
        source_fields: dict[str, str],
        fixture_format: str,
    ) -> None:

        nas_name = self._field(
            source_fields,
            "nas_name",
        )

        severity = self._field(
            source_fields,
            "severity",
        )

        raw_category = self._field(
            source_fields,
            "category",
        )

        application = (
            self._field(
                source_fields,
                "application",
            )
            or self._derive_application(
                notification.subject,
                notification.body,
            )
        )

        message_text = (
            self._field(
                source_fields,
                "message",
            )
            or notification.subject
            or "QNAP notification"
        )

        event_time = self._normalize_datetime(
            self._field(
                source_fields,
                "event_time",
            )
        )

        searchable = self._combined_text(
            notification.subject,
            notification.body,
            raw_category,
            application,
            message_text,
        )

        category = self._category(
            raw_category,
            searchable,
        )

        status = self._status(
            severity,
            searchable,
        )

        if not severity:

            severity = {
                "failure": "Error",
                "warning": "Warning",
                "success": "Normal",
                "information": "Information",
            }.get(
                status,
                "Information",
            )

        event_type = (
            self._field(
                source_fields,
                "event_type",
            )
            or self._derive_event_type(
                category,
                status,
                searchable,
            )
        )

        notification.category = category
        notification.status = status
        notification.title = (
            self._field(
                source_fields,
                "title",
            )
            or notification.subject
            or message_text
            or "QNAP notification"
        )

        if event_time:

            if (
                status == "success"
                or self._contains_any(
                    event_type.casefold(),
                    (
                        "completed",
                        "recovered",
                        "resolved",
                        "restored",
                    ),
                )
            ):

                notification.end_time = event_time

            else:

                notification.start_time = event_time

        notification.metadata = {
            "event_type": event_type,
            "severity": severity,
            "nas_name": nas_name,
            "application": application,
            "category": category,
            "message": message_text,
            "event_time": event_time,
            "source_fields": source_fields,
            "parser_confidence": self._parser_confidence(
                notification,
                source_fields,
            ),
            "fixture_format": fixture_format,
        }

    def _field(
        self,
        fields: dict[str, str],
        name: str,
    ) -> str:

        for alias in self.FIELD_ALIASES.get(
            name,
            (),
        ):

            value = fields.get(
                alias,
                "",
            )

            if value:

                return value

        return ""

    def _category(
        self,
        raw_category: str,
        searchable: str,
    ) -> str:

        normalized = str(
            raw_category
            or ""
        ).strip().casefold()

        if normalized in {
            "backup",
            "generic",
            "power",
            "security",
            "storage",
            "system",
        }:

            return normalized

        category_text = self._combined_text(
            raw_category,
            searchable,
        )

        for category in (
            "power",
            "security",
            "backup",
            "storage",
            "system",
        ):

            if self._contains_any(
                category_text,
                self.CATEGORY_KEYWORDS[category],
            ):

                return category

        return "generic"

    def _status(
        self,
        severity: str,
        searchable: str,
    ) -> str:

        severity_normalized = self._normalize_status_text(
            severity
            or ""
        )

        exact_severity_status = {
            "abnormal": "failure",
            "critical": "failure",
            "emergency": "failure",
            "error": "failure",
            "failed": "failure",
            "failure": "failure",
            "fatal": "failure",
            "high": "failure",
            "not ok": "failure",
            "not successful": "failure",
            "unsuccessful": "failure",
            "alert": "warning",
            "average": "warning",
            "degraded": "warning",
            "medium": "warning",
            "warn": "warning",
            "warning": "warning",
            "normal": "success",
            "ok": "success",
            "recovered": "success",
            "recovery": "success",
            "resolved": "success",
            "restored": "success",
            "success": "success",
            "succeeded": "success",
            "successful": "success",
            "completed": "success",
            "info": "information",
            "information": "information",
            "notice": "information",
        }

        exact_status = exact_severity_status.get(
            severity_normalized,
        )

        if exact_status:

            return exact_status

        # Explicit negative phrases are evaluated before positive terms.
        # Boundary-aware matching prevents "normal" in "abnormal" and
        # "successful" in "unsuccessful" from becoming success.
        precedence = (
            (
                "failure",
                (
                    "not successful",
                    "unsuccessful",
                    "not ok",
                    "abnormal",
                    "critical",
                    "emergency",
                    "error",
                    "errors",
                    "failed",
                    "failure",
                    "fatal",
                    "unable to",
                ),
            ),
            (
                "warning",
                (
                    "alert",
                    "degraded",
                    "warn",
                    "warning",
                    "threshold exceeded",
                ),
            ),
            (
                "success",
                (
                    "recovered",
                    "recovery",
                    "resolved",
                    "restored",
                    "normal",
                ),
            ),
            (
                "success",
                (
                    "completed successfully",
                    "completed",
                    "success",
                    "succeeded",
                    "successful",
                ),
            ),
            (
                "information",
                (
                    "information",
                    "info",
                    "notice",
                ),
            ),
        )

        for status, phrases in precedence:

            if self._contains_status_term(
                severity_normalized,
                phrases,
            ) or self._contains_status_term(
                searchable,
                phrases,
            ):

                return status

        return "information"

    def _normalize_status_text(
        self,
        value: str,
    ) -> str:

        value = html.unescape(
            str(
                value
                or ""
            )
        ).casefold()

        value = re.sub(
            r"[_-]+",
            " ",
            value,
        )

        return re.sub(
            r"\s+",
            " ",
            value,
        ).strip()

    def _contains_status_term(
        self,
        value: str,
        terms: tuple[str, ...],
    ) -> bool:

        normalized = self._normalize_status_text(
            value,
        )

        return any(
            re.search(
                rf"(?<!\w){re.escape(term)}(?!\w)",
                normalized,
            )
            for term in terms
        )

    def _derive_application(
        self,
        subject: str,
        body: str,
    ) -> str:

        searchable = self._combined_text(
            subject,
            body,
        )

        applications = (
            (
                "Hybrid Backup Sync",
                (
                    "hybrid backup sync",
                    "hbs 3",
                ),
            ),
            (
                "Storage & Snapshots",
                (
                    "storage & snapshots",
                    "storage pool",
                    "raid",
                    "s.m.a.r.t",
                ),
            ),
            (
                "QuLog Center",
                (
                    "qulog center",
                    "failed login",
                    "login failure",
                ),
            ),
            (
                "Notification Center",
                (
                    "notification center",
                    "test notification",
                ),
            ),
            (
                "App Center",
                (
                    "app center",
                    "application update",
                ),
            ),
            (
                "Firmware Update",
                (
                    "firmware update",
                    "firmware version",
                ),
            ),
            (
                "External Device",
                (
                    "ups",
                    "external device",
                ),
            ),
        )

        for application, keywords in applications:

            if self._contains_any(
                searchable,
                keywords,
            ):

                return application

        return ""

    def _derive_event_type(
        self,
        category: str,
        status: str,
        searchable: str,
    ) -> str:

        if self._contains_any(
            searchable,
            (
                "test message",
                "test notification",
            ),
        ):

            return "test_message"

        if self._contains_any(
            searchable,
            (
                "failed login",
                "login failure",
                "login attempt",
                "logon failure",
            ),
        ):

            return "failed_login"

        if self._contains_any(
            searchable,
            (
                "ups",
                "power outage",
                "power failure",
                "power restored",
            ),
        ):

            return "power_event"

        if self._contains_any(
            searchable,
            (
                "hybrid backup sync",
                "hbs 3",
                "backup",
                "replication",
                "sync job",
            ),
        ):

            if status == "failure":

                return "backup_failure"

            return "backup_event"

        if "raid" in searchable:

            return "raid_warning"

        if "storage pool" in searchable:

            return "storage_warning"

        if self._contains_any(
            searchable,
            (
                "disk warning",
                "disk error",
                "drive warning",
                "drive error",
                "s.m.a.r.t",
                "smart warning",
            ),
        ):

            return "disk_warning"

        if self._contains_any(
            searchable,
            (
                "firmware",
                "application update",
                "update available",
            ),
        ):

            return "update_notice"

        if category != "generic":

            return f"{category}_event"

        return "notification"

    def _normalize_datetime(
        self,
        value: str,
    ) -> str:

        value = str(
            value
            or ""
        ).strip()

        if not value:

            return ""

        value = re.sub(
            r"^at\s+",
            "",
            value,
            flags=re.IGNORECASE,
        )

        formats = (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
            "%Y.%m.%d %H:%M:%S",
            "%Y.%m.%d %H:%M",
            "%Y-%m-%dT%H:%M:%S",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
            "%b %d, %Y %H:%M:%S",
            "%B %d, %Y %H:%M:%S",
        )

        for fmt in formats:

            try:

                parsed = datetime.strptime(
                    value,
                    fmt,
                )

                return parsed.strftime(
                    "%Y-%m-%d %H:%M:%S",
                )

            except ValueError:

                continue

        return value

    def _parser_confidence(
        self,
        notification: Notification,
        source_fields: dict[str, str],
    ) -> str:

        recognized = sum(
            bool(
                self._field(
                    source_fields,
                    name,
                )
            )
            for name in (
                "application",
                "category",
                "event_time",
                "event_type",
                "message",
                "nas_name",
                "severity",
            )
        )

        branded = self._contains_any(
            self._combined_text(
                notification.sender,
                notification.subject,
                notification.body,
            ),
            (
                "qnap",
                "qts",
                "quts hero",
                "notification center",
            ),
        )

        if branded and recognized >= 5:

            return "high"

        if branded or recognized >= 2:

            return "medium"

        return "low"

    def _fixture_format(
        self,
        plain_parts: list[str],
        html_parts: list[str],
    ) -> str:

        if plain_parts and html_parts:

            return "multipart"

        if html_parts:

            return "html"

        if plain_parts:

            return "plain-text"

        return "unknown"

    def _combined_text(
        self,
        *values: str,
    ) -> str:

        return " ".join(
            str(
                value
                or ""
            )
            for value in values
        ).casefold()

    def _contains_any(
        self,
        value: str,
        keywords: tuple[str, ...],
    ) -> bool:

        return any(
            keyword in value
            for keyword in keywords
        )

    def _empty_metadata(self) -> dict:

        return {
            "event_type": "notification",
            "severity": "Information",
            "nas_name": "",
            "application": "",
            "category": "generic",
            "message": "",
            "event_time": "",
            "source_fields": {},
            "parser_confidence": "low",
            "fixture_format": "unknown",
        }

    def _log_summary(
        self,
        notification: Notification,
    ) -> None:

        metadata = notification.metadata or {}

        log.info("===== QNAP PARSED =====")

        log.info(
            "Event Type      : %s",
            metadata.get(
                "event_type",
                "",
            ),
        )

        log.info(
            "Category        : %s",
            notification.category,
        )

        log.info(
            "Status          : %s",
            notification.status,
        )

        log.info(
            "Severity        : %s",
            metadata.get(
                "severity",
                "",
            ),
        )

        log.info(
            "NAS Name        : %s",
            metadata.get(
                "nas_name",
                "",
            ),
        )

        log.info(
            "Application     : %s",
            metadata.get(
                "application",
                "",
            ),
        )

        log.info(
            "Message         : %s",
            metadata.get(
                "message",
                "",
            ),
        )

        log.info(
            "Event Time      : %s",
            metadata.get(
                "event_time",
                "",
            ),
        )

        log.info(
            "Confidence      : %s",
            metadata.get(
                "parser_confidence",
                "",
            ),
        )

        log.info(
            "Fixture Format  : %s",
            metadata.get(
                "fixture_format",
                "",
            ),
        )

        log.info("========================")
