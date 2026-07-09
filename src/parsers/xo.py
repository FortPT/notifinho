"""
Notifinho

xo.py

Parser for Xen Orchestra backup reports.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup
from email.message import EmailMessage

from logger import log
from models import Notification


class Parser:
    """
    Xen Orchestra backup report parser.
    """

    IGNORED_BOLD_LABELS = {
        "pool id",
        "uuid",
        "start time",
        "end time",
        "duration",
        "error",
        "size",
        "speed",
        "transfer",
        "snapshot",
        "remotes",
    }

    def parse(
        self,
        message: EmailMessage,
    ) -> Notification:

        notification = Notification()

        notification.source = "xo"
        notification.category = "backup"

        html = self._extract_html(message)

        soup = BeautifulSoup(
            html,
            "lxml",
        )

        self._parse_headers(
            notification,
            message,
        )

        self._parse_job_name(
            notification,
        )

        self._parse_summary(
            notification,
            soup,
        )

        self._parse_vm_sections(
            notification,
            soup,
        )

        self._finalize_transfer_info(
            notification,
        )

        self._set_compatibility_fields(
            notification,
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

        notification.sender = message.get(
            "From",
            "",
        )

        notification.subject = str(
            message.get(
                "Subject",
                "",
            )
        )

        notification.title = notification.subject

    def _parse_job_name(
        self,
        notification: Notification,
    ) -> None:

        match = re.search(
            r"Backup report for\s+\[(.*?)\]\s*(.+?)(?:\s+[🚨⚠️✅])?$",
            notification.subject,
        )

        if match:

            notification.job_name = (
                f"[{match.group(1)}] {match.group(2)}"
            )

            return

        notification.job_name = notification.subject

    def _parse_summary(
        self,
        notification: Notification,
        soup: BeautifulSoup,
    ) -> None:

        h1 = soup.find(
            "h1",
            string=re.compile(
                r"Global status",
                re.IGNORECASE,
            ),
        )

        if not h1:

            return

        notification.status = self._normalize_status(
            h1.get_text(
                " ",
                strip=True,
            )
        )

        ul = h1.find_next(
            "ul",
        )

        summary = self._parse_key_value_list(
            ul,
        )

        notification.job_id = summary.get(
            "job id",
            "",
        )

        notification.run_id = summary.get(
            "run id",
            "",
        )

        notification.mode = summary.get(
            "mode",
            "",
        )

        notification.start_time = summary.get(
            "start time",
            "",
        )

        notification.end_time = summary.get(
            "end time",
            "",
        )

        notification.duration = summary.get(
            "duration",
            "",
        )

        notification.transfer_size = summary.get(
            "transfer size",
            "",
        )

        self._parse_success_count(
            notification,
            summary.get(
                "successes",
                "",
            ),
        )

    def _parse_success_count(
        self,
        notification: Notification,
        value: str,
    ) -> None:

        match = re.search(
            r"(\d+)\s*/\s*(\d+)",
            value,
        )

        if not match:

            return

        success = int(
            match.group(1),
        )

        total = int(
            match.group(2),
        )

        failed = max(
            total - success,
            0,
        )

        notification.vm_success = success
        notification.vm_failed = failed
        notification.vm_total = total

    def _parse_vm_sections(
        self,
        notification: Notification,
        soup: BeautifulSoup,
    ) -> None:

        for h2 in soup.find_all("h2"):

            section_title = h2.get_text(
                " ",
                strip=True,
            )

            section_type = self._section_type(
                section_title,
            )

            if section_type is None:

                continue

            count = self._section_count(
                section_title,
            )

            vm_headers = self._vm_headers_until_next_h2(
                h2,
            )

            for h3 in vm_headers:

                vm_name = h3.get_text(
                    " ",
                    strip=True,
                )

                if not vm_name:

                    continue

                vm_block = self._elements_until_next_vm_or_section(
                    h3,
                )

                details = self._parse_vm_details(
                    vm_block,
                )

                notification.vm_details[vm_name] = details

                if section_type == "success":

                    self._append_unique(
                        notification.successful_vms,
                        vm_name,
                    )

                elif section_type == "failure":

                    self._append_unique(
                        notification.failed_vms,
                        vm_name,
                    )

                    error = details.get(
                        "error",
                        "",
                    )

                    if error:

                        self._append_unique(
                            notification.errors,
                            error,
                        )

                        if not notification.error:

                            notification.error = error

                elif section_type == "skipped":

                    self._append_unique(
                        notification.skipped_vms,
                        vm_name,
                    )

                    error = details.get(
                        "error",
                        "",
                    )

                    if error:

                        self._append_unique(
                            notification.errors,
                            error,
                        )

                        if not notification.error:

                            notification.error = error

            if count is not None:

                if section_type == "success":

                    notification.vm_success = count

                elif section_type == "failure":

                    notification.vm_failed = count

                elif section_type == "skipped":

                    notification.vm_skipped = count

        self._fix_missing_counts(
            notification,
        )

    def _vm_headers_until_next_h2(
        self,
        h2,
    ) -> list:

        headers = []

        for element in h2.find_all_next():

            name = getattr(
                element,
                "name",
                None,
            )

            if name == "h2":

                break

            if name == "h3":

                headers.append(
                    element,
                )

        return headers

    def _elements_until_next_vm_or_section(
        self,
        h3,
    ) -> list:

        elements = []

        for element in h3.find_all_next():

            if element is h3:

                continue

            name = getattr(
                element,
                "name",
                None,
            )

            if name in {
                "h2",
                "h3",
            }:

                break

            elements.append(
                element,
            )

        return elements

    def _parse_vm_details(
        self,
        elements: list,
    ) -> dict:

        details = {
            "repository": "",
            "speed": "",
            "size": "",
            "error": "",
        }

        for element in elements:

            if getattr(
                element,
                "name",
                None,
            ) != "li":

                continue

            text = element.get_text(
                " ",
                strip=True,
            )

            label, value = self._split_label_value(
                text,
            )

            if not label:

                continue

            label_lower = label.lower()

            if label_lower == "error":

                details["error"] = value

            elif label_lower == "speed":

                details["speed"] = value

            elif label_lower == "size":

                details["size"] = value

        repository = self._extract_repository(
            elements,
        )

        if repository:

            details["repository"] = repository

        return details

    def _extract_repository(
        self,
        elements: list,
    ) -> str:

        for element in elements:

            if getattr(
                element,
                "name",
                None,
            ) != "span":

                continue

            text = element.get_text(
                " ",
                strip=True,
            )

            clean = text.strip()

            if not clean:

                continue

            lower = clean.lower()

            if lower in self.IGNORED_BOLD_LABELS:

                continue

            if "|" not in clean:

                continue

            return clean

        return ""

    def _finalize_transfer_info(
        self,
        notification: Notification,
    ) -> None:

        #
        # Prefer repository/speed from successful VMs.
        # If no successful VM has it, fall back to failed/skipped.
        #

        ordered_vms = (
            notification.successful_vms
            + notification.failed_vms
            + notification.skipped_vms
        )

        for vm in ordered_vms:

            details = notification.vm_details.get(
                vm,
                {},
            )

            if not notification.repository and details.get("repository"):

                notification.repository = details["repository"]

            if not notification.transfer_speed and details.get("speed"):

                notification.transfer_speed = details["speed"]

            if notification.repository and notification.transfer_speed:

                break

    def _fix_missing_counts(
        self,
        notification: Notification,
    ) -> None:

        if notification.vm_success == 0 and notification.successful_vms:

            notification.vm_success = len(
                notification.successful_vms,
            )

        if notification.vm_failed == 0 and notification.failed_vms:

            notification.vm_failed = len(
                notification.failed_vms,
            )

        if notification.vm_skipped == 0 and notification.skipped_vms:

            notification.vm_skipped = len(
                notification.skipped_vms,
            )

        if notification.vm_total == 0:

            notification.vm_total = (
                notification.vm_success
                + notification.vm_failed
                + notification.vm_skipped
            )

    def _extract_html(
        self,
        message: EmailMessage,
    ) -> str:

        if message.is_multipart():

            for part in message.walk():

                if part.get_content_type() != "text/html":

                    continue

                payload = part.get_payload(
                    decode=True,
                )

                if payload is None:

                    continue

                charset = (
                    part.get_content_charset()
                    or "utf-8"
                )

                return payload.decode(
                    charset,
                    errors="replace",
                )

        payload = message.get_payload(
            decode=True,
        )

        if payload is None:

            return ""

        charset = (
            message.get_content_charset()
            or "utf-8"
        )

        return payload.decode(
            charset,
            errors="replace",
        )

    def _parse_key_value_list(
        self,
        ul,
    ) -> dict:

        data = {}

        if ul is None:

            return data

        for li in ul.find_all(
            "li",
            recursive=False,
        ):

            label_node = li.find(
                "span",
            )

            if label_node is None:

                continue

            label = label_node.get_text(
                " ",
                strip=True,
            ).lower()

            full_text = li.get_text(
                " ",
                strip=True,
            )

            value = full_text

            if ":" in full_text:

                value = full_text.split(
                    ":",
                    1,
                )[1].strip()

            data[label] = value

        return data

    def _split_label_value(
        self,
        text: str,
    ) -> tuple[str, str]:

        if ":" not in text:

            return "", ""

        label, value = text.split(
            ":",
            1,
        )

        return label.strip(), value.strip()

    def _normalize_status(
        self,
        status: str,
    ) -> str:

        status = status.lower()

        if "failure" in status:

            return "failure"

        if "failed" in status:

            return "failure"

        if "skip" in status:

            return "skipped"

        if "success" in status:

            return "success"

        return "info"

    def _section_type(
        self,
        title: str,
    ) -> str | None:

        title = title.lower()

        if "failure" in title or "failed" in title:

            return "failure"

        if "success" in title:

            return "success"

        if "skip" in title:

            return "skipped"

        return None

    def _section_count(
        self,
        title: str,
    ) -> int | None:

        match = re.search(
            r"(\d+)",
            title,
        )

        if not match:

            return None

        return int(
            match.group(1),
        )

    def _append_unique(
        self,
        values: list,
        value: str,
    ) -> None:

        if value and value not in values:

            values.append(
                value,
            )

    def _set_compatibility_fields(
        self,
        notification: Notification,
    ) -> None:

        notification.successes = notification.vm_success
        notification.failures = notification.vm_failed
        notification.skipped = notification.vm_skipped

        notification.vm_successes = notification.vm_success
        notification.vm_failures = notification.vm_failed

        notification.metadata["provider"] = "Xen Orchestra"
        notification.metadata["job_id"] = notification.job_id
        notification.metadata["run_id"] = notification.run_id
        notification.metadata["mode"] = notification.mode
        notification.metadata["repository"] = notification.repository
        notification.metadata["transfer_speed"] = notification.transfer_speed

    def _log_summary(
        self,
        notification: Notification,
    ) -> None:

        log.info("===== XO PARSED =====")

        log.info("Job Name      : %s", notification.job_name)
        log.info("Status        : %s", notification.status)
        log.info("Job ID        : %s", notification.job_id)
        log.info("Run ID        : %s", notification.run_id)
        log.info("Mode          : %s", notification.mode)
        log.info("Start         : %s", notification.start_time)
        log.info("End           : %s", notification.end_time)
        log.info("Duration      : %s", notification.duration)
        log.info("Transfer Size : %s", notification.transfer_size)
        log.info("Transfer Speed: %s", notification.transfer_speed)
        log.info("Repository    : %s", notification.repository)
        log.info("VM Success    : %s", notification.vm_success)
        log.info("VM Failed     : %s", notification.vm_failed)
        log.info("VM Skipped    : %s", notification.vm_skipped)
        log.info("Successful VMs: %s", notification.successful_vms)
        log.info("Failed VMs    : %s", notification.failed_vms)
        log.info("Skipped VMs   : %s", notification.skipped_vms)
        log.info("VM Details    : %s", notification.vm_details)
        log.info("Error         : %s", notification.error)

        log.info("=====================")
