"""Parsers for Synology DSM email and Notifinho webhook notifications."""

from __future__ import annotations

import html
import re

from email.message import EmailMessage

from bs4 import BeautifulSoup

from logger import log
from models import Notification


class Parser:
    """Normalize bounded Synology DSM SMTP and webhook events."""

    WEBHOOK_SCHEMA = "notifinho.synology.v1"
    SEVERITIES = {
        "debug",
        "info",
        "information",
        "notice",
        "warning",
        "warn",
        "error",
        "critical",
        "success",
    }
    CATEGORIES = {
        "availability",
        "backup",
        "disk",
        "network",
        "package",
        "power",
        "replication",
        "security",
        "storage",
        "system",
    }
    CATEGORY_MARKERS = (
        ("disk", ("s.m.a.r.t", "smart test", "bad sector", "drive", "disk")),
        ("backup", ("hyper backup", "active backup", "backup", "restore")),
        ("replication", ("snapshot replication", "replication", "replicate")),
        ("power", ("ups", "battery", "power supply", "power outage", "power recovered")),
        ("security", ("login", "authentication", "certificate", "malware", "blocked ip", "firewall")),
        ("package", ("package center", "package", "application", "service stopped")),
        ("network", ("network", "interface", "bond", "link down", "dns", "gateway")),
        ("availability", ("unavailable", "offline", "unreachable", "shutdown", "restarted")),
        ("storage", ("storage pool", "volume", "raid", "cache", "capacity", "space")),
        ("system", ("dsm", "system", "update", "temperature", "fan", "memory", "cpu")),
    )
    DIRECT_METADATA_KEYS = {
        "nas_name",
        "hostname",
        "host",
        "model",
        "serial",
        "storage",
        "storage_pool",
        "volume",
        "disk",
        "drive",
        "package",
        "task",
        "job",
        "username",
        "user",
        "ip_address",
        "source_ip",
    }

    def is_message(self, message: EmailMessage) -> bool:
        sender = self._header(message, "From").casefold()
        subject = self._header(message, "Subject").casefold()
        branded = any(
            marker in f"{sender} {subject}"
            for marker in ("synology", "diskstation")
        )
        if branded:
            return True
        return bool(
            re.search(r"\bdsm\b", subject)
            and any(marker in subject for marker in ("alert", "event", "notification"))
        )

    @classmethod
    def is_envelope(cls, payload) -> bool:
        if not isinstance(payload, dict):
            return False
        if payload.get("schema") != cls.WEBHOOK_SCHEMA:
            return False
        if str(payload.get("source", "")).casefold() not in {
            "synology",
            "synology-dsm",
            "dsm",
        }:
            return False
        if not any(
            isinstance(payload.get(key), str) and payload[key].strip()
            for key in ("title", "message")
        ):
            return False
        if str(payload.get("severity", "info")).casefold() not in cls.SEVERITIES:
            return False
        metadata = payload.get("metadata", {})
        if not isinstance(metadata, dict) or len(metadata) > 64:
            return False
        if not all(cls._scalar(value) for value in metadata.values()):
            return False
        bounded_keys = cls.DIRECT_METADATA_KEYS | {
            "event_type",
            "type",
            "status",
            "timestamp",
        }
        return all(
            key not in payload or cls._scalar(payload[key])
            for key in bounded_keys
        )

    def parse(self, source) -> Notification:
        if isinstance(source, dict):
            return self.parse_webhook(source)
        if not isinstance(source, EmailMessage):
            raise ValueError("unsupported Synology notification type")
        return self.parse_email(source)

    def parse_webhook(self, payload: dict) -> Notification:
        if not self.is_envelope(payload):
            raise ValueError("invalid Synology webhook envelope")

        metadata = {
            self._key(key): self._text(value)
            for key, value in (payload.get("metadata") or {}).items()
            if self._key(key) and self._scalar(value)
        }
        for key in self.DIRECT_METADATA_KEYS:
            if key in payload and self._scalar(payload[key]):
                metadata.setdefault(key, self._text(payload[key]))

        title = self._text(payload.get("title")) or "Synology DSM notification"
        message = self._text(payload.get("message")) or title
        severity = self._text(payload.get("severity") or "info").casefold()
        state = self._text(payload.get("status")).casefold()
        event_type = self._text(
            payload.get("event_type") or payload.get("type")
        ).casefold().replace("_", "-")
        category = (
            event_type
            if event_type in self.CATEGORIES
            else self._category(
                " ".join((title, message, event_type, " ".join(metadata.values())))
            )
        )
        status = (
            "success"
            if state in {"resolved", "recovered", "restored"}
            else self._status(" ".join((severity, state, title, message)))
        )
        event_time = self._text(payload.get("timestamp"))
        host = (
            metadata.get("nas_name")
            or metadata.get("hostname")
            or metadata.get("host", "")
        )

        notification = Notification(
            source="synology",
            category=category,
            status=status,
            title=title,
            subject=title,
            body=message,
            start_time=event_time,
            end_time=(
                event_time
                if status == "success" and state in {"resolved", "recovered"}
                else ""
            ),
        )
        notification.metadata = self._metadata(
            format_name="webhook",
            severity=severity,
            state=state or self._state(status),
            category=category,
            event_type=event_type,
            event_time=event_time,
            host=host,
            values=metadata,
            confidence="high",
        )
        return notification

    def parse_email(self, message: EmailMessage) -> Notification:
        subject = self._header(message, "Subject")
        sender = self._header(message, "From")
        notification = Notification(
            source="synology",
            category="generic",
            status="information",
            title=self._clean_title(subject),
            subject=subject,
            sender=sender,
        )

        try:
            plain_parts, html_parts = self._parts(message)
            body_candidates = plain_parts or [
                self._html_text(value) for value in html_parts
            ]
            raw_body = self._clean("\n\n".join(body_candidates))
            fields = self._fields(raw_body)
            event_message = self._event_message(raw_body, fields)
            combined = " ".join((subject, event_message, " ".join(fields.values())))
            notification.body = event_message or notification.title
            notification.category = self._category(combined)
            notification.status = self._status(combined)
            severity = self._field(fields, "severity", "level", "priority")
            severity = severity.casefold() or self._severity(
                combined,
                notification.status,
            )
            event_time = self._field(
                fields,
                "event time",
                "date/time",
                "timestamp",
                "time",
                "date",
            )
            host = self._field(
                fields,
                "nas name",
                "server name",
                "hostname",
                "host",
            ) or self._host(subject)
            values = {
                "nas_name": host,
                "hostname": host,
                "model": self._field(fields, "model", "model name"),
                "storage": self._field(fields, "storage", "storage pool"),
                "storage_pool": self._field(fields, "storage pool", "pool"),
                "volume": self._field(fields, "volume"),
                "disk": self._field(fields, "disk", "drive"),
                "package": self._field(fields, "package", "application"),
                "task": self._field(fields, "task", "job", "backup task"),
                "username": self._field(fields, "username", "user", "account"),
                "source_ip": self._field(fields, "source ip", "ip address", "ip"),
                "source_fields": fields,
            }
            notification.start_time = event_time
            notification.metadata = self._metadata(
                format_name=self._format(plain_parts, html_parts),
                severity=severity,
                state=self._state(notification.status),
                category=notification.category,
                event_type=self._field(fields, "event type", "event", "type"),
                event_time=event_time,
                host=host,
                values=values,
                confidence="medium",
            )
        except Exception:
            log.exception("Failed to fully parse Synology DSM email")
            notification.body = notification.body or notification.title
            notification.metadata = {
                "provider": "Synology DSM",
                "format": "malformed",
                "parser_confidence": "low",
                "validation": "synthetic-fixture",
            }
        return notification

    def _metadata(
        self,
        *,
        format_name: str,
        severity: str,
        state: str,
        category: str,
        event_type: str,
        event_time: str,
        host: str,
        values: dict,
        confidence: str,
    ) -> dict:
        return {
            "provider": "Synology DSM",
            "format": format_name,
            "schema": self.WEBHOOK_SCHEMA if format_name == "webhook" else "",
            "severity": severity,
            "state": state,
            "category": category,
            "event_type": event_type,
            "event_time": event_time,
            "host": host,
            "nas_name": values.get("nas_name") or host,
            "hostname": values.get("hostname") or host,
            "model": values.get("model", ""),
            "storage": values.get("storage", ""),
            "storage_pool": values.get("storage_pool", ""),
            "volume": values.get("volume", ""),
            "disk": values.get("disk") or values.get("drive", ""),
            "package": values.get("package", ""),
            "task": values.get("task") or values.get("job", ""),
            "username": values.get("username") or values.get("user", ""),
            "source_ip": values.get("source_ip") or values.get("ip_address", ""),
            "metadata": values if format_name == "webhook" else {},
            "source_fields": values.get("source_fields", {}),
            "parser_confidence": confidence,
            "validation": "synthetic-fixture",
        }

    def _parts(self, message: EmailMessage) -> tuple[list[str], list[str]]:
        plain, rich = [], []
        parts = list(message.walk()) if message.is_multipart() else [message]
        for part in parts:
            if str(part.get_content_disposition() or "").casefold() == "attachment":
                continue
            kind = str(part.get_content_type() or "").casefold()
            if kind not in {"text/plain", "text/html"}:
                continue
            value = self._decode(part)
            if value.strip():
                (rich if kind == "text/html" else plain).append(value)
        return plain, rich

    @staticmethod
    def _decode(part) -> str:
        try:
            value = part.get_content()
        except Exception:
            value = part.get_payload(decode=True)
        if isinstance(value, bytes):
            return value.decode(
                part.get_content_charset() or "utf-8",
                errors="replace",
            )
        return value if isinstance(value, str) else ""

    def _html_text(self, value: str) -> str:
        try:
            return self._clean(
                BeautifulSoup(value, "lxml").get_text("\n", strip=True)
            )
        except Exception:
            return self._clean(re.sub(r"<[^>]+>", "\n", value))

    @staticmethod
    def _clean(value: str) -> str:
        lines = []
        for raw in html.unescape(str(value or "")).splitlines():
            line = re.sub(r"\s+", " ", raw).strip()
            if line:
                lines.append(line)
        return "\n".join(lines)

    def _fields(self, body: str) -> dict[str, str]:
        result = {}
        for line in body.splitlines():
            match = re.match(
                r"^([A-Za-z][A-Za-z0-9 &/_-]{1,40})\s*:\s*(.{1,1000})$",
                line,
            )
            if match:
                result.setdefault(self._key(match.group(1)), match.group(2).strip())
        return result

    def _event_message(self, body: str, fields: dict[str, str]) -> str:
        labelled = self._field(
            fields,
            "message",
            "event message",
            "event",
            "description",
            "details",
        )
        if labelled:
            return labelled
        skip = (
            "dear user",
            "sincerely",
            "synology diskstation",
            "this message was generated",
        )
        candidates = [
            line
            for line in body.splitlines()
            if not line.casefold().startswith(skip) and ":" not in line[:42]
        ]
        return candidates[0] if candidates else ""

    def _category(self, value: str) -> str:
        text = f" {value.casefold()} "
        for category, markers in self.CATEGORY_MARKERS:
            if any(marker in text for marker in markers):
                return category
        return "system" if "synology" in text else "generic"

    @staticmethod
    def _status(value: str) -> str:
        text = value.casefold()
        if any(
            marker in text
            for marker in ("failed", "failure", "error", "critical", "fatal", "crashed")
        ):
            return "failure"
        if any(
            marker in text
            for marker in ("warning", "warn", "degraded", "low space", "attention")
        ):
            return "warning"
        if any(
            marker in text
            for marker in ("resolved", "recovered", "restored", "healthy", "success")
        ):
            return "success"
        return "information"

    @staticmethod
    def _severity(value: str, status: str) -> str:
        text = value.casefold()
        for severity in ("critical", "error", "warning", "notice", "info"):
            if re.search(rf"\b{severity}\b", text):
                return severity
        return {
            "failure": "error",
            "warning": "warning",
            "success": "success",
        }.get(status, "info")

    @staticmethod
    def _state(status: str) -> str:
        return {
            "failure": "failed",
            "warning": "warning",
            "success": "resolved",
        }.get(status, "information")

    @staticmethod
    def _host(subject: str) -> str:
        match = re.search(
            r"\b(?:from|on)\s+([A-Za-z0-9][A-Za-z0-9._-]{0,254})",
            subject,
            flags=re.I,
        )
        return match.group(1) if match else ""

    @staticmethod
    def _clean_title(subject: str) -> str:
        value = re.sub(
            r"^\s*\[(?:synology|dsm|synology nas)\]\s*",
            "",
            subject or "",
            flags=re.I,
        ).strip()
        return value or "Synology DSM notification"

    @staticmethod
    def _format(plain: list[str], rich: list[str]) -> str:
        if plain and rich:
            return "multipart"
        return "plain-text" if plain else "html"

    @staticmethod
    def _field(fields: dict[str, str], *names: str) -> str:
        for name in names:
            key = re.sub(
                r"[^a-z0-9_-]+",
                "_",
                str(name or "").strip().casefold(),
            ).strip("_")
            if fields.get(key):
                return fields[key]
        return ""

    @staticmethod
    def _header(message: EmailMessage, name: str) -> str:
        try:
            return str(message.get(name, "") or "").strip()
        except Exception:
            return ""

    @staticmethod
    def _key(value) -> str:
        return re.sub(
            r"[^a-z0-9_-]+",
            "_",
            str(value or "").strip().casefold(),
        ).strip("_")

    @staticmethod
    def _scalar(value) -> bool:
        return value is None or isinstance(value, (str, int, float, bool))

    @staticmethod
    def _text(value) -> str:
        return "" if value is None else str(value).strip()
