"""
Notifinho

zabbix.py

Parser for Zabbix email notifications.
"""

from __future__ import annotations

import re

from datetime import datetime
from email.message import EmailMessage

from bs4 import BeautifulSoup
from bs4.element import Tag

from logger import log
from models import Notification


class Parser:
    """
    Parse Zabbix problem and recovery email notifications.
    """

    def parse(
        self,
        message: EmailMessage,
    ) -> Notification:

        notification = Notification()

        notification.source = "zabbix"
        notification.category = "monitoring"

        self._parse_headers(
            notification,
            message,
        )

        content = self._extract_content(
            message,
        )

        notification.body = self._plain_text(
            content,
        )

        fields = self._parse_fields(
            content,
        )

        self._populate_notification(
            notification,
            fields,
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

        notification.sender = str(
            message.get(
                "From",
                "",
            )
        )

        notification.subject = str(
            message.get(
                "Subject",
                "",
            )
        )

    def _extract_content(
        self,
        message: EmailMessage,
    ) -> str:

        body = message.get_body(
            preferencelist=(
                "html",
                "plain",
            )
        )

        if body is not None:

            content = body.get_content()

            if isinstance(content, bytes):

                charset = body.get_content_charset() or "utf-8"

                return content.decode(
                    charset,
                    errors="replace",
                )

            return str(content)

        payload = message.get_payload(
            decode=True,
        )

        if isinstance(payload, bytes):

            charset = message.get_content_charset() or "utf-8"

            return payload.decode(
                charset,
                errors="replace",
            )

        return str(
            message.get_payload() or ""
        )

    def _plain_text(
        self,
        content: str,
    ) -> str:

        if not content:

            return ""

        soup = BeautifulSoup(
            content,
            "lxml",
        )

        for br in soup.find_all("br"):

            br.replace_with("\n")

        return soup.get_text(
            " ",
            strip=True,
        )

    def _parse_fields(
        self,
        content: str,
    ) -> dict[str, str]:

        if not content:

            return {}

        soup = BeautifulSoup(
            content,
            "lxml",
        )

        fields: dict[str, str] = {}

        for bold in soup.find_all(
            [
                "b",
                "strong",
            ]
        ):

            label = self._normalize_label(
                bold.get_text(
                    " ",
                    strip=True,
                )
            )

            if not label:

                continue

            value_parts = []

            for sibling in bold.next_siblings:

                if (
                    isinstance(sibling, Tag)
                    and sibling.name == "br"
                ):

                    break

                if isinstance(sibling, Tag):

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

            fields[label] = " ".join(
                value_parts,
            ).strip()

        return fields

    def _normalize_label(
        self,
        value: str,
    ) -> str:

        value = str(
            value or "",
        ).strip()

        value = value.rstrip(
            ":",
        )

        value = re.sub(
            r"\s+",
            " ",
            value,
        )

        return value.lower()

    def _populate_notification(
        self,
        notification: Notification,
        fields: dict[str, str],
    ) -> None:

        event_type = self._event_type(
            notification.subject,
            fields,
        )

        problem_name = (
            fields.get(
                "problem name",
                "",
            )
            or self._problem_name_from_subject(
                notification.subject,
            )
        )

        host = fields.get(
            "host",
            "",
        )

        severity = fields.get(
            "severity",
            "",
        )

        operational_data = fields.get(
            "operational data",
            "",
        )

        problem_id = fields.get(
            "original problem id",
            "",
        )

        duration = fields.get(
            "problem duration",
            "",
        )

        if event_type == "recovery":

            raw_event_time = fields.get(
                "problem has been resolved",
                "",
            )

            notification.status = "success"

            notification.end_time = self._normalize_datetime(
                raw_event_time,
            )

        else:

            raw_event_time = fields.get(
                "problem started",
                "",
            )

            notification.status = "failure"

            notification.start_time = self._normalize_datetime(
                raw_event_time,
            )

        notification.title = (
            problem_name
            or notification.subject
            or "Zabbix notification"
        )

        notification.duration = duration

        notification.metadata = {
            "event_type": event_type,
            "problem_name": problem_name,
            "host": host,
            "severity": severity,
            "operational_data": operational_data,
            "problem_id": problem_id,
            "event_time": self._normalize_datetime(
                raw_event_time,
            ),
            "fields": fields,
        }

    def _event_type(
        self,
        subject: str,
        fields: dict[str, str],
    ) -> str:

        subject_lower = str(
            subject or "",
        ).lower()

        if (
            "problem has been resolved" in fields
            or subject_lower.startswith("resolved")
        ):

            return "recovery"

        return "problem"

    def _problem_name_from_subject(
        self,
        subject: str,
    ) -> str:

        subject = str(
            subject or "",
        ).strip()

        subject = re.sub(
            r"^Problem:\s*",
            "",
            subject,
            flags=re.IGNORECASE,
        )

        subject = re.sub(
            r"^Resolved(?:\s+in\s+[^:]+)?:\s*",
            "",
            subject,
            flags=re.IGNORECASE,
        )

        return subject.strip()

    def _normalize_datetime(
        self,
        value: str,
    ) -> str:

        if not value:

            return ""

        value = str(
            value,
        ).strip()

        value = re.sub(
            r"^at\s+",
            "",
            value,
            flags=re.IGNORECASE,
        )

        formats = [
            "%H:%M:%S on %Y.%m.%d",
            "%H:%M on %Y.%m.%d",
            "%Y.%m.%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
        ]

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

    def _log_summary(
        self,
        notification: Notification,
    ) -> None:

        metadata = notification.metadata

        log.info("===== ZABBIX PARSED =====")

        log.info(
            "Event Type      : %s",
            metadata.get(
                "event_type",
                "",
            ),
        )

        log.info(
            "Status          : %s",
            notification.status,
        )

        log.info(
            "Problem         : %s",
            metadata.get(
                "problem_name",
                "",
            ),
        )

        log.info(
            "Host            : %s",
            metadata.get(
                "host",
                "",
            ),
        )

        log.info(
            "Severity        : %s",
            metadata.get(
                "severity",
                "",
            ),
        )

        log.info(
            "Operational Data: %s",
            metadata.get(
                "operational_data",
                "",
            ),
        )

        log.info(
            "Problem ID      : %s",
            metadata.get(
                "problem_id",
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
            "Duration        : %s",
            notification.duration,
        )

        log.info("=========================")
