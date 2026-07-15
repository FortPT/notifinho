"""Parsers for Proxmox VE email and Notifinho webhook notifications."""

from __future__ import annotations

import html
import re

from email.message import EmailMessage

from bs4 import BeautifulSoup

from logger import log
from models import Notification


class Parser:
    """Normalize bounded Proxmox VE SMTP and webhook events."""

    WEBHOOK_SCHEMA = "notifinho.proxmox.v1"
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
    CATEGORY_MARKERS = (
        ("backup", ("backup", "vzdump", "restore")),
        ("replication", ("replication", "replicate")),
        ("storage", ("storage", "ceph", "zfs", "pool", "disk", "volume")),
        ("cluster", ("cluster", "quorum", "corosync", "ha ", "high availability")),
        ("availability", ("offline", "unavailable", "unreachable", "fence", "node down")),
        ("security", ("authentication", "login", "certificate", "permission")),
        ("guest", ("virtual machine", " vm ", "qemu", "container", " lxc ", "guest")),
        ("system", ("node", "package", "update", "temperature", "memory", "cpu")),
    )

    def is_message(self, message: EmailMessage) -> bool:
        """Require Proxmox branding or a characteristic vzdump subject."""
        sender = self._header(message, "From").casefold()
        subject = self._header(message, "Subject").casefold()
        if "proxmox" in sender or "proxmox" in subject:
            return True
        return bool(
            re.search(r"\b(?:pve|vzdump)\b", subject)
            and any(marker in subject for marker in ("backup", "replication", "status"))
        )

    @classmethod
    def is_envelope(cls, payload) -> bool:
        """Validate the explicit Notifinho Proxmox webhook contract."""
        if not isinstance(payload, dict):
            return False
        if payload.get("schema") != cls.WEBHOOK_SCHEMA:
            return False
        if str(payload.get("source", "")).casefold() not in {
            "proxmox",
            "proxmox-ve",
            "pve",
        }:
            return False
        title = payload.get("title")
        message = payload.get("message")
        if not any(isinstance(value, str) and value.strip() for value in (title, message)):
            return False
        severity = str(payload.get("severity", "info")).casefold()
        if severity not in cls.SEVERITIES:
            return False
        metadata = payload.get("metadata", {})
        return isinstance(metadata, dict) and len(metadata) <= 64

    def parse(self, source) -> Notification:
        if isinstance(source, dict):
            return self.parse_webhook(source)
        if not isinstance(source, EmailMessage):
            raise ValueError("unsupported Proxmox notification type")
        return self.parse_email(source)

    def parse_webhook(self, payload: dict) -> Notification:
        if not self.is_envelope(payload):
            raise ValueError("invalid Proxmox webhook envelope")

        supplied = payload.get("metadata") or {}
        metadata = {
            self._key(key): self._text(value)
            for key, value in supplied.items()
            if self._key(key) and self._scalar(value)
        }
        title = self._text(payload.get("title")) or "Proxmox VE notification"
        message = self._text(payload.get("message")) or title
        severity = self._text(payload.get("severity") or "info").casefold()
        state = self._text(payload.get("status")).casefold()
        event_type = self._text(payload.get("type")).casefold().replace("_", "-")
        known_categories = {category for category, _markers in self.CATEGORY_MARKERS}
        category = (
            event_type
            if event_type in known_categories
            else self._category(
                " ".join((title, message, event_type, " ".join(metadata.values())))
            )
        )
        status = self._status(" ".join((severity, state, title, message)))
        event_time = self._text(payload.get("timestamp"))
        host = metadata.get("node") or metadata.get("host") or metadata.get("hostname", "")

        notification = Notification(
            source="proxmox",
            category=category,
            status=status,
            title=title,
            subject=title,
            body=message,
            start_time=event_time,
            end_time=event_time if status == "success" and state in {"resolved", "recovered"} else "",
        )
        notification.metadata = {
            "provider": "Proxmox VE",
            "format": "webhook",
            "schema": self.WEBHOOK_SCHEMA,
            "severity": severity,
            "state": state or self._state(status),
            "category": category,
            "event_type": event_type,
            "event_time": event_time,
            "host": host,
            "node": metadata.get("node", host),
            "vmid": metadata.get("vmid", ""),
            "guest": metadata.get("guest") or metadata.get("name", ""),
            "job_id": metadata.get("job_id") or metadata.get("job-id", ""),
            "storage": metadata.get("storage", ""),
            "metadata": metadata,
            "parser_confidence": "high",
            "validation": "synthetic-fixture",
        }
        return notification

    def parse_email(self, message: EmailMessage) -> Notification:
        subject = self._header(message, "Subject")
        sender = self._header(message, "From")
        notification = Notification(
            source="proxmox",
            category="generic",
            status="information",
            title=subject or "Proxmox VE notification",
            subject=subject,
            sender=sender,
        )

        try:
            plain_parts, html_parts = self._parts(message)
            body_candidates = plain_parts or [self._html_text(value) for value in html_parts]
            body = self._clean("\n\n".join(body_candidates))
            fields = self._fields(body)
            backup_rows = self._backup_rows(body)
            combined = " ".join((subject, body, " ".join(fields.values())))
            notification.body = body or subject
            notification.category = self._category(combined)
            notification.status = self._status(combined)
            notification.title = self._title(subject, notification.category, notification.status)
            notification.start_time = self._field(fields, "start time", "started", "timestamp", "date")
            notification.end_time = self._field(fields, "end time", "finished", "completed")
            notification.duration = self._field(fields, "duration", "total time")
            notification.job_id = self._field(fields, "job id", "job-id", "job")
            notification.repository = self._field(fields, "storage", "repository", "target")
            failed = [row for row in backup_rows if row["status"] not in {"ok", "success"}]
            successful = [row for row in backup_rows if row["status"] in {"ok", "success"}]
            notification.vm_total = len(backup_rows)
            notification.vm_success = len(successful)
            notification.vm_failed = len(failed)
            notification.successes = notification.vm_success
            notification.failures = notification.vm_failed
            notification.successful_vms = [row["label"] for row in successful]
            notification.failed_vms = [row["label"] for row in failed]
            if backup_rows:
                notification.body = self._backup_summary(
                    len(backup_rows),
                    len(successful),
                    len(failed),
                )
            if failed:
                notification.status = "failure"
                notification.errors = [row["message"] for row in failed if row["message"]]
                notification.error = notification.errors[0] if notification.errors else "Backup failed"

            host = self._field(fields, "node", "hostname", "host", "server") or self._host(subject, body)
            severity = self._severity(combined, notification.status)
            notification.metadata = {
                "provider": "Proxmox VE",
                "format": self._format(plain_parts, html_parts),
                "severity": severity,
                "state": self._state(notification.status),
                "category": notification.category,
                "event_type": self._event_type(notification.category, subject),
                "event_time": notification.start_time,
                "host": host,
                "node": host,
                "vmid": self._field(fields, "vmid", "guest id"),
                "guest": self._field(fields, "guest", "guest name", "vm name", "container"),
                "job_id": notification.job_id,
                "storage": notification.repository,
                "source_fields": fields,
                "backup_rows": backup_rows,
                "parser_confidence": "medium",
                "validation": "synthetic-fixture",
            }
        except Exception:
            log.exception("Failed to fully parse Proxmox email")
            notification.body = notification.body or subject
            notification.metadata = {
                "provider": "Proxmox VE",
                "format": "malformed",
                "parser_confidence": "low",
                "validation": "synthetic-fixture",
            }
        return notification

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
            return value.decode(part.get_content_charset() or "utf-8", errors="replace")
        return value if isinstance(value, str) else ""

    def _html_text(self, value: str) -> str:
        try:
            return self._clean(BeautifulSoup(value, "lxml").get_text("\n", strip=True))
        except Exception:
            return self._clean(re.sub(r"<[^>]+>", "\n", value))

    @staticmethod
    def _clean(value: str) -> str:
        return "\n".join(
            line for line in (re.sub(r"\s+", " ", raw).strip() for raw in html.unescape(str(value or "")).splitlines()) if line
        )

    def _fields(self, body: str) -> dict[str, str]:
        result = {}
        for line in body.splitlines():
            match = re.match(r"^([A-Za-z][A-Za-z0-9 _/-]{1,40})\s*:\s*(.{1,1000})$", line)
            if match:
                result.setdefault(self._key(match.group(1)), match.group(2).strip())
        return result

    def _backup_rows(self, body: str) -> list[dict[str, str]]:
        rows = []
        for line in body.splitlines():
            match = re.match(
                r"^(\d{1,9})\s+(.+?)\s+(OK|SUCCESS|ERROR|FAILED|FAILURE|WARNING)"
                r"(?:\s+([0-9:]+))?(?:\s+([0-9.]+\s*[KMGT]i?B))?(?:\s+(.*))?$",
                line,
                flags=re.I,
            )
            if not match:
                continue
            vmid, name, state, duration, size, detail = match.groups()
            label = f"{vmid} | {name.strip()}"
            rows.append(
                {
                    "vmid": vmid,
                    "name": name.strip(),
                    "label": label,
                    "status": state.casefold(),
                    "duration": duration or "",
                    "size": size or "",
                    "message": (detail or "").strip(),
                }
            )
        return rows

    @staticmethod
    def _backup_summary(total: int, successful: int, failed: int) -> str:
        guest_label = "guest" if total == 1 else "guests"
        if failed:
            failed_label = "guest" if failed == 1 else "guests"
            return (
                f"Backup completed with errors: {failed} {failed_label} "
                f"failed out of {total} {guest_label}."
            )
        return (
            f"Backup completed successfully for {successful} {guest_label}."
        )

    def _category(self, value: str) -> str:
        text = f" {value.casefold()} "
        for category, markers in self.CATEGORY_MARKERS:
            if any(marker in text for marker in markers):
                return category
        return "generic"

    @staticmethod
    def _status(value: str) -> str:
        text = value.casefold()
        if any(
            marker in text
            for marker in (
                "failed",
                "failure",
                "error",
                "critical",
                "fatal",
                "unsuccessful",
                "not ok",
            )
        ):
            return "failure"
        if any(marker in text for marker in ("warning", "warn", "degraded", "unknown")):
            return "warning"
        if any(marker in text for marker in ("resolved", "recovered", "successful", "success", "status: ok")):
            return "success"
        return "information"

    @staticmethod
    def _severity(value: str, status: str) -> str:
        text = value.casefold()
        for severity in ("critical", "error", "warning", "notice", "info"):
            if re.search(rf"\b{severity}\b", text):
                return severity
        return {"failure": "error", "warning": "warning", "success": "success"}.get(status, "info")

    @staticmethod
    def _state(status: str) -> str:
        return {"failure": "failed", "warning": "warning", "success": "success"}.get(status, "information")

    @staticmethod
    def _event_type(category: str, subject: str) -> str:
        return category if category != "generic" else (subject or "notification")

    @staticmethod
    def _title(subject: str, category: str, status: str) -> str:
        if subject:
            return re.sub(r"^\s*\[?proxmox(?:\s+ve)?\]?\s*[-:]?\s*", "", subject, flags=re.I) or subject
        label = category.replace("_", " ").title()
        return f"Proxmox {label} {status}" if category != "generic" else "Proxmox VE notification"

    @staticmethod
    def _host(subject: str, body: str) -> str:
        for value in (subject, body):
            match = re.search(r"\b(?:node|host)\s+['\"]?([A-Za-z0-9][A-Za-z0-9._-]{0,254})", value, flags=re.I)
            if match:
                return match.group(1)
        return ""

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
            value = fields.get(key)
            if value:
                return value
        return ""

    @staticmethod
    def _header(message: EmailMessage, name: str) -> str:
        try:
            return str(message.get(name, "") or "").strip()
        except Exception:
            return ""

    @staticmethod
    def _key(value) -> str:
        return re.sub(r"[^a-z0-9_-]+", "_", str(value or "").strip().casefold()).strip("_")

    @staticmethod
    def _scalar(value) -> bool:
        return value is None or isinstance(value, (str, int, float, bool))

    @staticmethod
    def _text(value) -> str:
        return "" if value is None else str(value).strip()
