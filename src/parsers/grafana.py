"""
Notifinho

grafana.py

Provisional parser for Grafana Alerting email notifications.
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
    """Parse synthetic and partially supported Grafana alert emails."""

    FIELD_ALIASES = {
        "alert_count": (
            "alert count",
            "alerts",
            "number of alerts",
        ),
        "alert_name": (
            "alert name",
            "alert",
            "name",
        ),
        "alert_rule": (
            "alert rule",
            "alert rule name",
            "rule",
            "rule name",
        ),
        "dashboard": (
            "dashboard",
            "dashboard name",
        ),
        "dashboard_url": (
            "dashboardurl",
            "dashboard url",
            "grafana_url",
            "grafana url",
        ),
        "datasource": (
            "data source",
            "datasource",
            "datasource name",
        ),
        "description": (
            "description",
            "details",
        ),
        "ends_at": (
            "ends at",
            "endsat",
            "ended at",
            "resolved at",
        ),
        "event_time": (
            "event time",
            "time",
            "timestamp",
        ),
        "folder": (
            "folder",
            "grafana folder",
        ),
        "labels": (
            "labels",
            "alert labels",
        ),
        "message": (
            "message",
            "notification message",
        ),
        "organization": (
            "org",
            "organization",
            "organization name",
        ),
        "panel": (
            "panel",
            "panel name",
        ),
        "panel_url": (
            "panelurl",
            "panel url",
        ),
        "rule_url": (
            "alert rule url",
            "ruleurl",
            "rule url",
        ),
        "severity": (
            "level",
            "priority",
            "severity",
        ),
        "silence_url": (
            "silenceurl",
            "silence url",
        ),
        "starts_at": (
            "starts at",
            "startsat",
            "started at",
        ),
        "state": (
            "alert state",
            "state",
            "status",
        ),
        "summary": (
            "summary",
            "title",
        ),
        "values": (
            "alert values",
            "value",
            "values",
        ),
    }

    def parse(
        self,
        message: EmailMessage,
    ) -> Notification:

        notification = Notification(
            source="grafana",
            category="generic",
            status="information",
        )

        notification.sender = self._header(
            message,
            "From",
        )

        notification.subject = self._header(
            message,
            "Subject",
        )

        notification.title = (
            notification.subject
            or "Grafana notification"
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

            self._populate_notification(
                notification,
                source_fields,
                self._fixture_format(
                    plain_parts,
                    html_parts,
                ),
            )

        except Exception:

            log.exception(
                "Failed to fully parse Grafana email"
            )

        self._log_summary(
            notification,
        )

        return notification

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
                ).casefold()

                disposition = str(
                    part.get_content_disposition()
                    or ""
                ).casefold()

            except Exception:

                continue

            if (
                disposition == "attachment"
                or content_type not in {
                    "text/plain",
                    "text/html",
                }
            ):

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

        return content if isinstance(content, str) else ""

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

        return "\n".join(
            line
            for raw_line in str(
                content
                or ""
            ).splitlines()
            if (
                line := re.sub(
                    r"\s+",
                    " ",
                    raw_line,
                ).strip()
            )
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

                    if value:

                        fields[label] = value
                        current_label = label

                    continue

            if (
                current_label
                and current_label in {
                    "description",
                    "details",
                    "message",
                    "summary",
                }
            ):

                fields[current_label] = self._append_value(
                    fields.get(
                        current_label,
                        "",
                    ),
                    line,
                )

        return fields

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
                ]
            )

            if len(cells) >= 2:

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

            if description is not None:

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

                if getattr(
                    sibling,
                    "name",
                    None,
                ) == "br":

                    break

                value = (
                    sibling.get_text(
                        " ",
                        strip=True,
                    )
                    if getattr(
                        sibling,
                        "name",
                        None,
                    )
                    else str(
                        sibling,
                    ).strip()
                )

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
            self._looks_like_label(label)
            and value
            and not fields.get(label)
        ):

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
        ).replace(
            "\xa0",
            " ",
        ).strip()

        return re.sub(
            r"\s+",
            " ",
            value.strip(
                "[]",
            ).rstrip(
                ":",
            ),
        ).strip().casefold()

    def _looks_like_label(
        self,
        label: str,
    ) -> bool:

        if not label or len(label) > 80:

            return False

        return bool(
            re.fullmatch(
                r"[a-z][\w\s/&().+#-]*",
                label,
                flags=re.IGNORECASE,
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

        values = {
            name: self._field(
                source_fields,
                name,
            )
            for name in self.FIELD_ALIASES
        }

        state = (
            values["state"]
            or self._state_from_subject(
                notification.subject,
            )
        )

        summary = values["summary"]
        description = values["description"]
        message_text = (
            values["message"]
            or summary
            or description
            or notification.subject
            or "Grafana notification"
        )

        searchable = self._combined_text(
            notification.subject,
            notification.body,
            state,
            values["severity"],
            message_text,
        )

        status = self._status(
            state,
            values["severity"],
            searchable,
        )

        category = self._category(
            state,
            searchable,
            values,
        )

        starts_at = self._normalize_datetime(
            values["starts_at"],
        )

        ends_at = self._normalize_datetime(
            values["ends_at"],
        )

        event_time = (
            ends_at
            if status == "success" and ends_at
            else starts_at
            or ends_at
            or self._normalize_datetime(
                values["event_time"],
            )
        )

        alert_rule = values["alert_rule"]
        alert_name = (
            values["alert_name"]
            or alert_rule
            or self._title_from_subject(
                notification.subject,
            )
        )

        notification.category = category
        notification.status = status
        notification.title = (
            alert_name
            or notification.subject
            or "Grafana notification"
        )

        if event_time:

            if status == "success":

                notification.end_time = event_time

            else:

                notification.start_time = event_time

        alert_count = self._alert_count(
            values["alert_count"],
            notification.subject,
            alert_name,
        )

        notification.metadata = {
            "alert_name": alert_name,
            "alert_rule": alert_rule,
            "rule_name": alert_rule,
            "state": state or self._state_from_status(status),
            "severity": values["severity"] or self._severity_from_status(status),
            "folder": values["folder"],
            "dashboard": values["dashboard"],
            "panel": values["panel"],
            "organization": values["organization"],
            "datasource": values["datasource"],
            "labels": values["labels"],
            "values": values["values"],
            "summary": summary,
            "description": description,
            "message": message_text,
            "starts_at": starts_at,
            "ends_at": ends_at,
            "event_time": event_time,
            "dashboard_url": values["dashboard_url"],
            "panel_url": values["panel_url"],
            "silence_url": values["silence_url"],
            "rule_url": values["rule_url"],
            "alert_count": alert_count,
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

    def _state_from_subject(
        self,
        subject: str,
    ) -> str:

        subject_text = str(
            subject
            or ""
        ).casefold()

        ordered = (
            ("not resolved", "Not Resolved"),
            ("no data", "No Data"),
            ("resolved", "Resolved"),
            ("pending", "Pending"),
            ("firing", "Firing"),
            ("error", "Error"),
            ("test", "Test"),
        )

        for marker, state in ordered:

            if marker in subject_text:

                return state

        return ""

    def _title_from_subject(
        self,
        subject: str,
    ) -> str:

        value = re.sub(
            r"^\[[^]]+\]\s*",
            "",
            str(
                subject
                or ""
            ).strip(),
        )

        return value.strip()

    def _status(
        self,
        state: str,
        severity: str,
        searchable: str,
    ) -> str:

        state_normalized = self._normalize_status_text(
            state,
        )

        severity_normalized = self._normalize_status_text(
            severity,
        )

        exact = {
            "abnormal": "failure",
            "critical": "failure",
            "error": "failure",
            "failed": "failure",
            "failure": "failure",
            "firing": "failure",
            "not ok": "failure",
            "not resolved": "failure",
            "not successful": "failure",
            "unsuccessful": "failure",
            "alert": "warning",
            "no data": "warning",
            "nodata": "warning",
            "pending": "warning",
            "warning": "warning",
            "warn": "warning",
            "normal": "success",
            "recovered": "success",
            "recovery": "success",
            "resolved": "success",
            "restored": "success",
            "completed": "success",
            "success": "success",
            "succeeded": "success",
            "successful": "success",
            "info": "information",
            "information": "information",
            "notice": "information",
            "test": "information",
        }

        for value in (
            state_normalized,
            severity_normalized,
        ):

            if value in exact:

                return exact[value]

        precedence = (
            (
                "failure",
                (
                    "not resolved",
                    "not successful",
                    "unsuccessful",
                    "not ok",
                    "abnormal",
                    "critical",
                    "error",
                    "failed",
                    "failure",
                    "firing",
                ),
            ),
            (
                "warning",
                (
                    "no data",
                    "pending",
                    "warning",
                    "warn",
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
                    "test notification",
                ),
            ),
        )

        combined = self._combined_text(
            state_normalized,
            severity_normalized,
            searchable,
        )

        for status, terms in precedence:

            if self._contains_status_term(
                combined,
                terms,
            ):

                return status

        return "information"

    def _normalize_status_text(
        self,
        value: str,
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

    def _contains_status_term(
        self,
        value: str,
        terms: tuple[str, ...],
    ) -> bool:

        return any(
            re.search(
                rf"(?<!\w){re.escape(term)}(?!\w)",
                value,
            )
            for term in terms
        )

    def _category(
        self,
        state: str,
        searchable: str,
        values: dict[str, str],
    ) -> str:

        if self._contains_status_term(
            searchable,
            (
                "data source error",
                "datasource error",
                "evaluation error",
            ),
        ) or values.get(
            "datasource"
        ) and self._contains_status_term(
            searchable,
            (
                "error",
                "failed",
            ),
        ):

            return "datasource"

        if self._contains_status_term(
            self._combined_text(
                state,
                searchable,
            ),
            (
                "test notification",
                "contact point test",
            ),
        ) or self._normalize_status_text(state) == "test":

            return "system"

        if (
            values.get("alert_name")
            or values.get("alert_rule")
            or self._contains_status_term(
                searchable,
                (
                    "firing",
                    "no data",
                    "pending",
                    "resolved",
                ),
            )
        ):

            return "alerting"

        return "generic"

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

        formats = (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%dT%H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%Y.%m.%d %H:%M:%S",
            "%d/%m/%Y %H:%M:%S",
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

    def _alert_count(
        self,
        value: str,
        subject: str,
        alert_name: str,
    ) -> int:

        match = re.search(
            r"\d+",
            str(
                value
                or ""
            ),
        )

        if not match:

            match = re.search(
                r"\[(?:firing|resolved)\s*:\s*(\d+)\]",
                str(
                    subject
                    or ""
                ),
                flags=re.IGNORECASE,
            )

        if match:

            return int(
                match.group(
                    1
                    if match.lastindex
                    else 0
                )
            )

        return 1 if alert_name else 0

    def _parser_confidence(
        self,
        notification: Notification,
        source_fields: dict[str, str],
    ) -> str:

        branded = "grafana" in self._combined_text(
            notification.sender,
            notification.subject,
            notification.body,
        )

        recognized = sum(
            bool(
                self._field(
                    source_fields,
                    name,
                )
            )
            for name in (
                "alert_name",
                "alert_rule",
                "dashboard",
                "folder",
                "message",
                "severity",
                "state",
                "summary",
            )
        )

        if branded and recognized >= 5:

            return "high"

        if branded or recognized >= 3:

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
        *values,
    ) -> str:

        return " ".join(
            str(
                value
                or ""
            )
            for value in values
        ).casefold()

    def _state_from_status(
        self,
        status: str,
    ) -> str:

        return {
            "failure": "Firing",
            "warning": "Warning",
            "success": "Resolved",
            "information": "Information",
        }.get(
            status,
            "Information",
        )

    def _severity_from_status(
        self,
        status: str,
    ) -> str:

        return {
            "failure": "Critical",
            "warning": "Warning",
            "success": "Normal",
            "information": "Information",
        }.get(
            status,
            "Information",
        )

    def _empty_metadata(self) -> dict:

        return {
            "alert_name": "",
            "alert_rule": "",
            "rule_name": "",
            "state": "Information",
            "severity": "Information",
            "folder": "",
            "dashboard": "",
            "panel": "",
            "organization": "",
            "datasource": "",
            "labels": "",
            "values": "",
            "summary": "",
            "description": "",
            "message": "",
            "starts_at": "",
            "ends_at": "",
            "event_time": "",
            "dashboard_url": "",
            "panel_url": "",
            "silence_url": "",
            "rule_url": "",
            "alert_count": 0,
            "source_fields": {},
            "parser_confidence": "low",
            "fixture_format": "unknown",
        }

    def _log_summary(
        self,
        notification: Notification,
    ) -> None:

        metadata = notification.metadata or {}

        log.info("===== GRAFANA PARSED =====")
        log.info("Alert Name      : %s", metadata.get("alert_name", ""))
        log.info("State           : %s", metadata.get("state", ""))
        log.info("Status          : %s", notification.status)
        log.info("Category        : %s", notification.category)
        log.info("Severity        : %s", metadata.get("severity", ""))
        log.info("Alert Rule      : %s", metadata.get("alert_rule", ""))
        log.info("Folder          : %s", metadata.get("folder", ""))
        log.info("Dashboard       : %s", metadata.get("dashboard", ""))
        log.info("Datasource      : %s", metadata.get("datasource", ""))
        log.info("Event Time      : %s", metadata.get("event_time", ""))
        log.info("Alert Count     : %s", metadata.get("alert_count", 0))
        log.info("Confidence      : %s", metadata.get("parser_confidence", ""))
        log.info("Fixture Format  : %s", metadata.get("fixture_format", ""))
        log.info("===========================")
