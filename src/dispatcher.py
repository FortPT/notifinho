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

from parsers.grafana import Parser as GrafanaParser
from parsers.generic import Parser as GenericParser
from parsers.proxmox import Parser as ProxmoxParser
from parsers.qnap import Parser as QnapParser
from parsers.truenas import Parser as TrueNASParser
from parsers.unifi_drive import Parser as UniFiDriveParser
from parsers.unifi_network import Parser as UniFiNetworkParser
from parsers.unifi_protect import Parser as UniFiProtectParser
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

        self.grafana_parser = GrafanaParser()

        self.unifi_drive_parser = UniFiDriveParser()

        self.unifi_network_parser = UniFiNetworkParser()

        self.unifi_protect_parser = UniFiProtectParser()

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

        unifi_drive_candidate = self.unifi_drive_parser.is_message(
            message,
        )

        if unifi_drive_candidate:

            # The Drive From display may contain a private system name.
            log.info(
                "Subject : [UniFi Drive notification]"
            )

            log.info(
                "Sender  : notifications.ui.com"
            )

        else:

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
        # Grafana
        #

        if self._is_grafana_email(
            message,
            sender,
            subject,
        ):

            log.info(
                "Detected Grafana email"
            )

            return self.grafana_parser.parse(
                message,
            )

        #
        # TrueNAS
        #
        # Run content-based TrueNAS detection after the established
        # integration detectors. This prevents vendor content in quoted
        # mail from stealing QNAP or Grafana messages.
        #

        if self._is_truenas_email(
            message,
            sender,
            subject,
        ):

            log.info(
                "Detected TrueNAS email"
            )

            return self.truenas_parser.parse(
                message,
            )

        #
        # UniFi Drive
        #

        if unifi_drive_candidate:

            log.info(
                "Detected UniFi Drive email"
            )

            return self.unifi_drive_parser.parse(
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

    def parse_webhook(self, application: str, payload):
        """Validate and parse a supported webhook into the shared model."""

        parsers = {
            "network": (
                self.unifi_network_parser,
                "Detected UniFi Network webhook",
            ),
            "protect": (
                self.unifi_protect_parser,
                "Detected UniFi Protect webhook",
            ),
        }
        selected = parsers.get(str(application).casefold())
        if selected is None:
            return None
        parser, log_message = selected
        if not parser.is_envelope(payload):
            return None
        log.info(log_message)
        return parser.parse(payload)

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

    def _is_grafana_email(
        self,
        message: EmailMessage,
        sender: str,
        subject: str,
    ) -> bool:
        """Detect Grafana Alerting mail using strong vendor signals."""

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
            "grafana",
            "grafana alerting",
        )

        weak_markers = (
            "alert",
            "dashboard",
            "firing",
            "no data",
            "notification",
            "resolved",
        )

        structured_markers = (
            "alert name",
            "alert rule",
            "dashboard",
            "endsat",
            "grafana folder",
            "labels",
            "panel",
            "startsat",
            "values",
        )

        url_markers = (
            "dashboardurl",
            "grafana_url",
            "panelurl",
            "ruleurl",
            "silenceurl",
            "/alerting/grafana/",
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

        subject_weak = self._contains_any(
            subject_text,
            weak_markers,
        )

        body_weak = self._contains_any(
            body_text,
            weak_markers,
        )

        structured_count = sum(
            marker in body_text
            for marker in structured_markers
        )

        url_count = sum(
            marker in body_text
            for marker in url_markers
        )

        # Explicit Grafana sender identity is trusted even when a contact
        # point uses a sparse custom body.
        if sender_brand:

            return True

        if subject_brand and (
            body_brand
            or body_weak
            or structured_count >= 1
            or url_count >= 1
        ):

            return True

        if body_brand and (
            subject_weak
            or structured_count >= 2
            or url_count >= 1
        ):

            return True

        # Grafana-specific fields and link names may remain after branding
        # is removed by a custom template. Weak alert words still do not
        # contribute enough evidence on their own.
        if (
            "grafana folder" in body_text
            and structured_count >= 3
        ):

            return True

        return bool(
            url_count >= 1
            and structured_count >= 2
        )

    def _is_truenas_email(
        self,
        message: EmailMessage,
        sender: str,
        subject: str,
    ) -> bool:
        """Detect TrueNAS alert-service mail using corroborating signals."""

        sender_text = str(sender or "").casefold()
        subject_text = str(subject or "").casefold().strip()
        body_text = self._truenas_detection_body(message).casefold()

        header_text = " ".join(
            f"{name} {value}"
            for name, value in message.items()
            if str(name).casefold() in {
                "reply-to",
                "return-path",
                "sender",
                "user-agent",
                "x-mailer",
                "x-truenas",
                "x-truenas-alert",
            }
        ).casefold()

        sender_brand = "truenas" in sender_text
        header_brand = "truenas" in header_text
        subject_brand = "truenas" in subject_text
        alerts_subject = subject_text == "alerts"

        body_lines = [
            line.strip()
            for line in body_text.splitlines()
            if line.strip()
        ]
        opening_lines = "\n".join(body_lines[:8])
        product_header = bool(
            re.search(
                r"(?im)^\s*truenas\s*@\s*[^\s<]{1,255}\s*$",
                opening_lines,
            )
        )
        test_alert = "this is a test alert" in body_text
        structure_markers = (
            "new alert:",
            "new alerts:",
            "the following alert has been cleared:",
            "these alerts have been cleared:",
            "current alerts:",
        )
        structure_count = sum(
            marker in body_text
            for marker in structure_markers
        )

        # A branded sender or dedicated header is useful, but requires an
        # alert-oriented corroborating signal. The generic subject "Alerts"
        # is never sufficient on its own.
        if (sender_brand or header_brand) and (
            alerts_subject
            or product_header
            or test_alert
            or structure_count >= 1
        ):
            return True

        if product_header and (
            alerts_subject
            or subject_brand
            or test_alert
            or structure_count >= 1
        ):
            return True

        return bool(
            subject_brand
            and product_header
            and (test_alert or structure_count >= 1)
        )

    def _truenas_detection_body(
        self,
        message: EmailMessage,
    ) -> str:
        """Return visible, non-attachment, non-quoted text for detection."""

        try:
            parts = list(message.walk()) if message.is_multipart() else [message]
        except Exception:
            parts = [message]

        contents = []

        for part in parts:
            try:
                content_type = str(part.get_content_type() or "").casefold()
                disposition = str(part.get_content_disposition() or "").casefold()
            except Exception:
                continue

            if disposition == "attachment" or content_type not in {
                "text/plain",
                "text/html",
            }:
                continue

            content = self._detection_part_text(part)

            if content_type == "text/html":
                try:
                    soup = BeautifulSoup(content, "lxml")
                    for element in soup.find_all(["script", "style", "blockquote"]):
                        element.decompose()
                    for element in soup.find_all(True):
                        marker = " ".join(
                            [
                                str(element.get("id", "")),
                                " ".join(element.get("class", [])),
                            ]
                        ).casefold()
                        if "quote" in marker or "forward" in marker:
                            element.decompose()
                    content = soup.get_text("\n", strip=True)
                except Exception:
                    content = self._searchable_html(content)

            kept_lines = []
            for line in str(content or "").splitlines():
                clean = line.strip()
                if re.search(
                    r"(?:original message|begin forwarded message|forwarded message)",
                    clean,
                    flags=re.IGNORECASE,
                ):
                    break
                if clean.startswith(">"):
                    continue
                kept_lines.append(line)

            contents.append("\n".join(kept_lines))

        return "\n".join(contents)

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
