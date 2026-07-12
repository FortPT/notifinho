"""
Notifinho

dispatcher.py

Receives email messages and dispatches them to the
appropriate parser based on their source.
"""

from __future__ import annotations

import re

from email.message import EmailMessage

from bs4 import BeautifulSoup

from logger import log

from parsers.generic import Parser as GenericParser
from parsers.proxmox import Parser as ProxmoxParser
from parsers.qnap import Parser as QnapParser
from parsers.truenas import Parser as TrueNASParser
from parsers.xo import Parser as XOParser
from parsers.zabbix import Parser as ZabbixParser


class Dispatcher:

    def __init__(self):

        self.generic_parser = GenericParser()

        self.xo_parser = XOParser()

        self.zabbix_parser = ZabbixParser()

        self.truenas_parser = TrueNASParser()

        self.proxmox_parser = ProxmoxParser()

        self.qnap_parser = QnapParser()

        log.info("Dispatcher initialized")

    def parse(
        self,
        message: EmailMessage,
    ):

        subject = str(
            message.get(
                "Subject",
                "",
            )
        )

        sender = str(
            message.get(
                "From",
                "",
            )
        )

        sender_lower = sender.lower()

        log.info(
            "Subject : %s",
            subject,
        )

        log.info(
            "Sender  : %s",
            sender,
        )

        #
        # Xen Orchestra
        #

        if "xen orchestra" in sender_lower:

            log.info(
                "Detected Xen Orchestra email"
            )

            return self.xo_parser.parse(
                message,
            )

        #
        # Zabbix
        #

        if "zabbix" in sender_lower:

            log.info(
                "Detected Zabbix email"
            )

            return self.zabbix_parser.parse(
                message,
            )

        #
        # TrueNAS
        #

        if "truenas" in sender_lower:

            log.info(
                "Detected TrueNAS email"
            )

            return self.truenas_parser.parse(
                message,
            )

        #
        # Proxmox
        #

        if "proxmox" in sender_lower:

            log.info(
                "Detected Proxmox email"
            )

            return self.proxmox_parser.parse(
                message,
            )

        #
        # QNAP
        #
        # Keep this content-based detector after the existing
        # sender-specific detectors so their precedence is unchanged.
        #

        if self._is_qnap_email(
            message,
            sender,
            subject,
        ):

            log.info(
                "Detected QNAP email"
            )

            return self.qnap_parser.parse(
                message,
            )

        #
        # Generic
        #

        log.info(
            "Using generic parser"
        )

        return self.generic_parser.parse(
            message,
        )

    def _is_qnap_email(
        self,
        message: EmailMessage,
        sender: str,
        subject: str,
    ) -> bool:
        """
        Detect QNAP messages using independent branding,
        product and structured-body signals.

        Generic NAS terminology is deliberately not sufficient.
        """

        sender_text = str(
            sender
            or ""
        ).casefold()

        subject_text = str(
            subject
            or ""
        ).casefold()

        body_text = self._detection_body(
            message,
        ).casefold()

        strong_brand_markers = (
            "qnap",
            "qts",
            "quts hero",
        )

        strong_product_markers = (
            "storage & snapshots",
            "hybrid backup sync",
            "hbs 3",
            "qulog center",
        )

        weak_product_markers = (
            "notification center",
            "nas",
            "system notification",
        )

        field_markers = (
            "nas name",
            "severity",
            "application",
            "app name",
            "event time",
            "date/time",
            "category",
            "message",
        )

        sender_brand = self._contains_any(
            sender_text,
            strong_brand_markers,
        )

        subject_brand = self._contains_any(
            subject_text,
            strong_brand_markers,
        )

        body_brand = self._contains_any(
            body_text,
            strong_brand_markers,
        )

        subject_product = self._contains_any(
            subject_text,
            strong_product_markers,
        )

        body_product = self._contains_any(
            body_text,
            strong_product_markers,
        )

        subject_weak_product = self._contains_any(
            subject_text,
            weak_product_markers,
        )

        body_weak_product = self._contains_any(
            body_text,
            weak_product_markers,
        )

        structured_fields = sum(
            marker in body_text
            for marker in field_markers
        )

        # An explicit QNAP/QTS/QuTS sender marker is a trusted strong
        # signal and must still detect sparse Notification Center mail.
        if sender_brand:

            return True

        # Strong branding elsewhere must be paired with message structure
        # or an alert-oriented weak/product signal. Weak markers alone are
        # never sufficient.
        if subject_brand and (
            body_brand
            or body_product
            or body_weak_product
            or subject_product
            or subject_weak_product
            or structured_fields >= 1
        ):

            return True

        if body_brand and (
            body_product
            or body_weak_product
            or subject_product
            or subject_weak_product
            or structured_fields >= 2
        ):

            return True

        return bool(
            (subject_product or body_product)
            and structured_fields >= 4
        )

    def _detection_body(
        self,
        message: EmailMessage,
    ) -> str:

        try:

            parts = (
                list(message.walk())
                if message.is_multipart()
                else [message]
            )

        except Exception:

            parts = [message]

        contents = []

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

            content = self._detection_part_text(
                part,
            )

            if content_type == "text/html":

                content = self._searchable_html(
                    content,
                )

            if content:

                contents.append(
                    content,
                )

        return "\n".join(
            contents,
        )

    def _searchable_html(
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

            return soup.get_text(
                " ",
                strip=True,
            )

        except Exception:

            return re.sub(
                r"<[^>]+>",
                " ",
                content,
            )

    def _detection_part_text(
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

    def _contains_any(
        self,
        value: str,
        markers: tuple[str, ...],
    ) -> bool:

        return any(
            re.search(
                rf"(?<![a-z0-9]){re.escape(marker)}(?![a-z0-9])",
                value,
                flags=re.IGNORECASE,
            )
            for marker in markers
        )
