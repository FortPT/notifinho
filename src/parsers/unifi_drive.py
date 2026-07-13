"""Provisional parser for UniFi Drive notification email."""

from __future__ import annotations

import html
import re

from email.message import EmailMessage
from email.utils import parseaddr, parsedate_to_datetime
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from models import Notification


class Parser:
    """Detect and normalize Drive email without mailbox-access concerns."""

    EVENT_RULES = (
        (
            "failure",
            "critical",
            "backup",
            (
                "backup task failed",
                "encryption failure",
                "decryption failure",
            ),
        ),
        (
            "failure",
            "critical",
            "storage",
            (
                "storage pool suspended",
                "drive failed",
                "shared drive full",
            ),
        ),
        (
            "warning",
            "warning",
            "backup",
            (
                "backup task partially completed",
                "backup task paused",
                "backup destination unavailable",
                "backup source unavailable",
            ),
        ),
        (
            "warning",
            "warning",
            "storage",
            ("ssd cache not found",),
        ),
        (
            "success",
            "information",
            "backup",
            ("backup task completed",),
        ),
        (
            "information",
            "information",
            "storage",
            ("storage pool expanded", "drive decrypted"),
        ),
        (
            "information",
            "information",
            "administration",
            ("setting changed", "settings changed", "administrative change"),
        ),
    )

    @classmethod
    def is_message(cls, message: EmailMessage) -> bool:
        sender = cls._header(message, "From")
        domain = parseaddr(sender)[1].rsplit("@", 1)[-1].casefold()
        if domain != "notifications.ui.com":
            return False
        subject = cls._header(message, "Subject")
        plain, html_parts = cls._parts(message)
        visible = "\n".join(plain or [cls._html_text(part) for part in html_parts])
        identity = f"{sender}\n{subject}\n{visible}".casefold()
        drive_identity = "unifi drive" in identity or (
            "unifi os" in sender.casefold() and "backup task" in identity
        )
        event_vocabulary = any(
            marker in identity
            for _, _, _, markers in cls.EVENT_RULES
            for marker in markers
        ) or all(marker in identity for marker in ("backup task", "remote backup"))
        unknown_event_evidence = (
            "unifi drive" in identity
            and "unifi os" in sender.casefold()
            and any(
                marker in identity
                for marker in (
                    "alert",
                    "backup",
                    "notification",
                    "notice",
                    "setting",
                    "storage",
                    "task",
                )
            )
        )
        return bool(drive_identity and (event_vocabulary or unknown_event_evidence))

    def parse(self, message: EmailMessage) -> Notification:
        subject = self._header(message, "Subject") or "UniFi Drive notification"
        sender = self._header(message, "From")
        plain_parts, html_parts = self._parts(message)
        used_html = not plain_parts
        body = self._clean_text(
            "\n\n".join(
                plain_parts
                if plain_parts
                else [self._html_text(part) for part in html_parts]
            )
        )
        status, severity, category, state = self._classify(subject, body)
        task_name, body_system = self._task_and_system(body)
        system = self._system_from_sender(sender) or body_system
        action_link = self._action_link(message, html_parts, body)
        original_time = self._original_timestamp(message)

        notification = Notification(
            source="unifi_drive",
            category=category,
            status=status,
            title=subject,
            subject=subject,
            body=self._details(body, subject),
            sender=sender,
            job_name=task_name,
            start_time=original_time,
        )
        notification.metadata = {
            "provider": "UniFi Drive",
            "system": system,
            "host": system,
            "event_title": subject,
            "backup_task": task_name,
            "event_state": state,
            "message": notification.body,
            "action_link": action_link,
            "category": category,
            "severity": severity,
            "parser_confidence": "high" if task_name or system else "medium",
            "event_time": original_time,
            "format": "html" if used_html else "plain",
        }
        return notification

    def _classify(self, subject: str, body: str) -> tuple[str, str, str, str]:
        """Return provisional normalized state, severity, category, and label."""

        text = f"{subject}\n{body}".casefold()
        for status, severity, category, markers in self.EVENT_RULES:
            matched = next((marker for marker in markers if marker in text), "")
            if matched:
                return status, severity, category, self._event_state(matched, status)
        return "information", "information", "generic", "unknown"

    def _event_state(self, marker: str, status: str) -> str:
        for token in (
            "partially completed",
            "suspended",
            "paused",
            "unavailable",
            "not found",
            "expanded",
            "decrypted",
            "full",
            "completed",
            "failed",
            "failure",
            "changed",
        ):
            if token in marker:
                return "failed" if token == "failure" else token
        return status

    def _task_and_system(self, body: str) -> tuple[str, str]:
        match = re.search(
            r"(?im)^\s*(?:the\s+)?backup task\s+([^\n]+?)\s+on\s+([^\n]+?)\s+was\s+"
            r"(?:completed partially|partially completed|completed|paused|failed)\b",
            body,
        )
        if not match:
            return "", ""
        return self._clean_value(match.group(1)), self._clean_value(match.group(2))

    def _system_from_sender(self, sender: str) -> str:
        display = parseaddr(sender)[0]
        if "," not in display or "unifi os" not in display.casefold():
            return ""
        return self._clean_value(display.split(",", 1)[1])

    def _details(self, body: str, subject: str) -> str:
        ignored = {
            subject.casefold(),
            "manage backup task",
            "unifi drive",
        }
        kept = []
        for line in body.splitlines():
            clean = line.strip()
            folded = clean.casefold()
            if not clean or folded in ignored:
                continue
            if re.fullmatch(r"https?://\S+", clean, flags=re.IGNORECASE):
                continue
            if folded.startswith("manage backup task:"):
                continue
            signature = folded.strip(" .,!:-")
            if signature in {
                "best regards",
                "kind regards",
                "regards",
                "the ubiquiti team",
                "warm regards",
            }:
                continue
            if any(
                marker in folded
                for marker in (
                    "contact support",
                    "copyright",
                    "do not reply",
                    "help center",
                    "manage email preferences",
                    "need help?",
                    "privacy policy",
                    "postal address",
                    "support center",
                    "terms of service",
                    "this email was sent",
                    "unsubscribe",
                    "view in browser",
                    "all rights reserved",
                )
            ):
                continue
            kept.append(clean)
        return "\n".join(kept[:12]) or subject

    def _action_link(
        self,
        message: EmailMessage,
        html_parts: list[str],
        body: str,
    ) -> str:
        for content in html_parts:
            try:
                soup = BeautifulSoup(content, "lxml")
                for anchor in soup.find_all("a", href=True):
                    label = anchor.get_text(" ", strip=True).casefold()
                    if "manage backup task" in label:
                        valid = self._valid_url(anchor.get("href"))
                        if valid:
                            return valid
            except Exception:
                continue
        for candidate in re.findall(r"https?://[^\s<>\"']+", body):
            valid = self._valid_url(candidate.rstrip(".,);"))
            if valid:
                return valid
        return ""

    def _valid_url(self, value) -> str:
        text = str(value or "").strip()
        try:
            parsed = urlsplit(text)
        except ValueError:
            return ""
        return text if parsed.scheme in {"http", "https"} and parsed.netloc else ""

    def _original_timestamp(self, message: EmailMessage) -> str:
        value = self._header(message, "Date")
        if not value:
            return ""
        try:
            return parsedate_to_datetime(value).isoformat()
        except (TypeError, ValueError, OverflowError):
            return value

    @staticmethod
    def _parts(message: EmailMessage) -> tuple[list[str], list[str]]:
        plain: list[str] = []
        html_parts: list[str] = []
        try:
            parts = list(message.walk()) if message.is_multipart() else [message]
        except Exception:
            parts = [message]
        for part in parts:
            try:
                kind = str(part.get_content_type() or "").casefold()
                disposition = str(part.get_content_disposition() or "").casefold()
            except Exception:
                continue
            if disposition == "attachment" or kind not in {"text/plain", "text/html"}:
                continue
            try:
                content = part.get_content()
            except Exception:
                payload = part.get_payload(decode=True) or b""
                content = payload.decode(
                    part.get_content_charset() or "utf-8",
                    errors="replace",
                )
            if isinstance(content, str) and content.strip():
                (plain if kind == "text/plain" else html_parts).append(content)
        return plain, html_parts

    @staticmethod
    def _html_text(content: str) -> str:
        try:
            soup = BeautifulSoup(content, "lxml")
            for element in soup.find_all(
                ["style", "script", "head", "noscript", "svg", "footer"]
            ):
                element.decompose()
            for image in soup.find_all("img"):
                image.decompose()
            return Parser._clean_text(soup.get_text("\n", strip=True))
        except Exception:
            return Parser._clean_text(re.sub(r"<[^>]+>", "\n", content))

    @staticmethod
    def _clean_text(content: str) -> str:
        lines = []
        for line in html.unescape(str(content or "")).splitlines():
            clean = re.sub(r"\s+", " ", line).strip()
            if clean:
                lines.append(clean)
        return "\n".join(lines)

    @staticmethod
    def _clean_value(value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip(" .,:;<>\"'")

    @staticmethod
    def _header(message: EmailMessage, name: str) -> str:
        try:
            return str(message.get(name, "") or "").strip()
        except Exception:
            return ""
