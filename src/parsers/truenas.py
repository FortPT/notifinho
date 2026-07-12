"""Provisional parser for TrueNAS 26 alert-service email."""

from __future__ import annotations

import html
import re

from email.message import EmailMessage

from bs4 import BeautifulSoup

from logger import log
from models import Notification


class Parser:
    """Parse the upstream TrueNAS alert-service text/list layout."""

    SECTION_PATTERNS = (
        (re.compile(r"^new alerts?\s*:?$", re.I), "new"),
        (
            re.compile(
                r"^(?:the following alert has|these alerts have) been cleared\s*:?$",
                re.I,
            ),
            "cleared",
        ),
        (re.compile(r"^current alerts?\s*:?$", re.I), "current"),
    )

    CATEGORY_KEYWORDS = (
        (
            "power",
            ("ups", "battery", "utility power", "mains power", "power supply"),
        ),
        (
            "security",
            (
                "security",
                "certificate",
                "authentication",
                "login",
                "unauthorized",
                "audit",
                "malware",
            ),
        ),
        (
            "network",
            (
                "network",
                "interface",
                "link down",
                "default route",
                "dns",
                "ethernet",
            ),
        ),
        (
            "backup",
            (
                "replication",
                "backup",
                "snapshot task",
                "cloud sync",
                "rsync",
                "task failed",
            ),
        ),
        (
            "storage",
            (
                "pool",
                "zfs",
                "disk",
                "drive",
                "smart",
                "s.m.a.r.t",
                "scrub",
                "sector",
                "checksum",
                "volume",
            ),
        ),
        (
            "applications",
            (
                "application",
                "service",
                "container",
                "kubernetes",
                "catalog",
                "plugin",
            ),
        ),
        (
            "system",
            (
                "system",
                "temperature",
                "memory",
                "cpu",
                "fan",
                "update",
                "boot",
                "failover",
            ),
        ),
    )

    TITLE_KEYWORDS = (
        ("smart", "SMART alert"),
        ("s.m.a.r.t", "SMART alert"),
        ("scrub", "Scrub alert"),
        ("replication", "Replication alert"),
        ("backup", "Backup task alert"),
        ("ups", "UPS power alert"),
        ("battery", "UPS power alert"),
        ("pool", "Pool health alert"),
        ("disk", "Disk health alert"),
        ("drive", "Disk health alert"),
        ("network", "Network alert"),
        ("security", "Security alert"),
        ("service", "Service alert"),
        ("application", "Application alert"),
    )

    def parse(self, message: EmailMessage) -> Notification:
        notification = Notification(
            source="truenas",
            category="generic",
            status="information",
        )
        notification.sender = self._header(message, "From")
        notification.subject = self._header(message, "Subject")
        notification.title = notification.subject or "TrueNAS notification"

        try:
            plain_parts, html_parts = self._extract_parts(message)
            html_texts = [self._html_text(value) for value in html_parts]
            candidates = html_texts or plain_parts
            notification.body = self._clean_text("\n\n".join(candidates))

            host = self._hostname(notification.body)
            alerts = []
            for content in candidates:
                alerts.extend(self._parse_content(content))
            alerts = self._deduplicate(alerts)

            if not alerts and notification.body:
                fallback = self._fallback_message(notification.body, host)
                if fallback:
                    alerts = [self._build_alert("unknown", fallback)]

            self._populate(notification, host, alerts, plain_parts, html_parts)
        except Exception:
            log.exception("Failed to fully parse TrueNAS email")
            notification.metadata = self._metadata(
                host="",
                alerts=[],
                fixture_format="malformed",
                confidence="low",
            )

        self._log_summary(notification)
        return notification

    def _header(self, message: EmailMessage, name: str) -> str:
        try:
            return str(message.get(name, "") or "").strip()
        except Exception:
            return ""

    def _extract_parts(
        self,
        message: EmailMessage,
    ) -> tuple[list[str], list[str]]:
        plain_parts: list[str] = []
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
            content = self._decode(part)
            if not content.strip():
                continue
            (html_parts if kind == "text/html" else plain_parts).append(content)

        if not plain_parts and not html_parts:
            fallback = self._decode(message)
            if fallback.strip():
                plain_parts.append(fallback)
        return plain_parts, html_parts

    def _decode(self, part) -> str:
        try:
            content = part.get_content()
        except Exception:
            try:
                content = part.get_payload(decode=True)
            except Exception:
                try:
                    content = part.get_payload()
                except Exception:
                    return ""
        if isinstance(content, bytes):
            charset = part.get_content_charset() or "utf-8"
            try:
                return content.decode(charset, errors="replace")
            except LookupError:
                return content.decode("utf-8", errors="replace")
        return content if isinstance(content, str) else ""

    def _html_text(self, content: str) -> str:
        try:
            soup = BeautifulSoup(content, "lxml")
            for element in soup.find_all(["script", "style"]):
                element.decompose()
            return self._clean_text(soup.get_text("\n", strip=True))
        except Exception:
            return self._clean_text(re.sub(r"<[^>]+>", "\n", content))

    def _clean_text(self, content: str) -> str:
        lines = []
        for raw_line in html.unescape(str(content or "")).splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            if line:
                lines.append(line)
        return "\n".join(lines)

    def _hostname(self, content: str) -> str:
        match = re.search(
            r"(?im)^\s*truenas\s*@\s*([^\s<>]{1,255})\s*$",
            content,
        )
        return match.group(1).strip() if match else ""

    def _parse_content(self, content: str) -> list[dict]:
        lines = [line.strip() for line in self._clean_text(content).splitlines()]
        if any("this is a test alert" in line.casefold() for line in lines):
            return [self._build_alert("test", "This is a test alert")]

        alerts = []
        section = ""
        for line in lines:
            if re.match(r"^truenas\s*@\s*", line, flags=re.I):
                continue
            matched_section = ""
            for pattern, event_type in self.SECTION_PATTERNS:
                if pattern.match(line):
                    matched_section = event_type
                    break
            if matched_section:
                section = matched_section
                continue
            if not section:
                continue
            message = re.sub(r"^[*\-\u2022]+\s*", "", line).strip()
            if message:
                alerts.append(self._build_alert(section, message))
        return alerts

    def _build_alert(self, event_type: str, message: str) -> dict:
        category = self._category(message)
        status, severity = self._state(event_type, message)
        return {
            "event_type": event_type,
            "title": self._title(message, event_type),
            "message": message,
            "category": category,
            "status": status,
            "severity": severity,
            "event_time": self._event_time(message),
            "recovery": event_type == "cleared",
        }

    def _category(self, message: str) -> str:
        value = message.casefold()
        for category, markers in self.CATEGORY_KEYWORDS:
            if any(marker in value for marker in markers):
                return category
        return "generic"

    def _title(self, message: str, event_type: str) -> str:
        if event_type == "test":
            return "TrueNAS test alert"
        value = message.casefold()
        for marker, title in self.TITLE_KEYWORDS:
            if marker in value:
                return title
        if event_type == "cleared":
            return "Cleared TrueNAS alert"
        return "TrueNAS alert"

    def _state(self, event_type: str, message: str) -> tuple[str, str]:
        if event_type == "cleared":
            return "success", "normal"
        if event_type == "test":
            return "information", "information"
        value = message.casefold()
        if any(
            marker in value
            for marker in (
                "critical",
                "emergency",
                "fatal",
                "faulted",
                "unhealthy",
                "failed",
                "failure",
                "error",
            )
        ):
            return "failure", "critical"
        if any(
            marker in value
            for marker in (
                "warning",
                "degraded",
                "on battery",
                "smart",
                "s.m.a.r.t",
                "offline",
            )
        ):
            return "warning", "warning"
        return "warning", "warning"

    def _event_time(self, message: str) -> str:
        match = re.search(
            r"\b(20\d{2}[-/]\d{2}[-/]\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?)\b",
            message,
        )
        return match.group(1) if match else ""

    def _deduplicate(self, alerts: list[dict]) -> list[dict]:
        unique = []
        seen = set()
        for alert in alerts:
            key = (alert.get("event_type"), alert.get("message"))
            if key not in seen:
                seen.add(key)
                unique.append(alert)
        return unique

    def _fallback_message(self, body: str, host: str) -> str:
        ignored = {f"truenas @ {host}".casefold(), "alerts"}
        for line in body.splitlines():
            if line.casefold() not in ignored:
                return line
        return ""

    def _populate(
        self,
        notification: Notification,
        host: str,
        alerts: list[dict],
        plain_parts: list[str],
        html_parts: list[str],
    ) -> None:
        notification.items = alerts
        fixture_format = (
            "multipart"
            if plain_parts and html_parts
            else "html"
            if html_parts
            else "plain"
        )
        confidence = "high" if host and alerts else "medium" if alerts else "low"

        if alerts:
            primary = self._primary_alert(alerts)
            notification.category = primary["category"]
            notification.status = primary["status"]
            notification.title = (
                primary["title"]
                if len(alerts) == 1
                else f"TrueNAS alerts ({len(alerts)})"
            )
            notification.body = "\n".join(item["message"] for item in alerts)
            event_time = next(
                (item["event_time"] for item in alerts if item["event_time"]),
                "",
            )
            if primary["recovery"]:
                notification.end_time = event_time
            else:
                notification.start_time = event_time

        notification.metadata = self._metadata(
            host=host,
            alerts=alerts,
            fixture_format=fixture_format,
            confidence=confidence,
        )

    def _primary_alert(self, alerts: list[dict]) -> dict:
        rank = {"failure": 4, "warning": 3, "success": 2, "information": 1}
        return max(alerts, key=lambda item: rank.get(item.get("status", ""), 0))

    def _metadata(
        self,
        host: str,
        alerts: list[dict],
        fixture_format: str,
        confidence: str,
    ) -> dict:
        primary = self._primary_alert(alerts) if alerts else {}
        event_types = list(dict.fromkeys(item["event_type"] for item in alerts))
        return {
            "provider": "TrueNAS",
            "host": host,
            "hostname": host,
            "event_type": primary.get("event_type", "unknown"),
            "event_types": event_types,
            "event_title": primary.get("title", "TrueNAS notification"),
            "message": primary.get("message", ""),
            "severity": primary.get("severity", "information"),
            "event_time": primary.get("event_time", ""),
            "alert_count": len(alerts),
            "categories": list(
                dict.fromkeys(item["category"] for item in alerts)
            ),
            "recovery": any(item["recovery"] for item in alerts),
            "alerts": alerts,
            "parser_confidence": confidence,
            "format": fixture_format,
        }

    def _log_summary(self, notification: Notification) -> None:
        metadata = notification.metadata or {}
        log.info("===== TRUENAS PARSED =====")
        log.info("Host          : %s", metadata.get("host", ""))
        log.info("Event type    : %s", metadata.get("event_type", ""))
        log.info("Alert count   : %s", metadata.get("alert_count", 0))
        log.info("Category      : %s", notification.category)
        log.info("Status        : %s", notification.status)
        log.info("Severity      : %s", metadata.get("severity", ""))
        log.info("Confidence    : %s", metadata.get("parser_confidence", ""))
        log.info("===========================")
