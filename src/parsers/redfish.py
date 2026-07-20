"""Shared Redfish Event Service and hardware-management email parsing."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re

from email.message import EmailMessage
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from models import Notification


_SEVERITY = {
    "critical": "failure",
    "fatal": "failure",
    "emergency": "failure",
    "alert": "failure",
    "warning": "warning",
    "caution": "warning",
    "ok": "success",
    "normal": "success",
    "cleared": "success",
    "informational": "information",
    "information": "information",
    "info": "information",
}

_VENDORS = {
    "supermicro": {
        "source": "supermicro",
        "name": "Supermicro BMC",
        "markers": ("supermicro", "sum", "smc"),
    },
    "hpe": {
        "source": "hpe_ilo",
        "name": "HPE iLO",
        "markers": ("hpe", "hewlett packard enterprise", "ilo", "hpemsg"),
    },
    "dell": {
        "source": "dell_idrac",
        "name": "Dell iDRAC",
        "markers": ("dell", "idrac", "lifecycle controller", "idracmsg"),
    },
}


def _clean(value, limit: int = 2000) -> str:
    text = " ".join(str(value or "").replace("\x00", " ").split())
    return text[:limit]


def _status(severity: str, message: str) -> tuple[str, str]:
    severity_text = _clean(severity, 64).casefold()
    message_text = _clean(message).casefold()
    if any(
        marker in message_text
        for marker in (
            "cleared",
            "recovered",
            "resolved",
            "restored",
            "returned to normal",
        )
    ):
        return "success", severity_text or "ok"
    normalized = _SEVERITY.get(severity_text)
    if normalized:
        return normalized, severity_text
    if any(marker in message_text for marker in ("critical", "failed", "failure")):
        return "failure", severity_text or "critical"
    if any(marker in message_text for marker in ("warning", "degraded", "threshold")):
        return "warning", severity_text or "warning"
    return "information", severity_text or "information"


def _category(*values: str) -> str:
    text = " ".join(_clean(value).casefold() for value in values)
    rules = (
        ("security", ("auth", "intrusion", "login", "security", "tamper")),
        ("power", ("power", "psu", "supply", "voltage", "battery")),
        ("thermal", ("thermal", "temperature", "fan", "cooling", "overheat")),
        ("memory", ("dimm", "memory", "ecc")),
        ("storage", ("disk", "drive", "raid", "storage", "volume", "controller")),
        ("firmware", ("bios", "firmware", "lifecycle", "update")),
        ("network", ("ethernet", "link", "network", "nic")),
        ("chassis", ("chassis", "enclosure", "sensor")),
        ("availability", ("boot", "reset", "shutdown", "unavailable")),
    )
    for category, markers in rules:
        if any(marker in text for marker in markers):
            return category
    return "hardware"


def _source_ip(message: str) -> str:
    """Return the first valid address emitted in a hardware event message."""

    for candidate in re.findall(r"[0-9A-Fa-f:.]+", _clean(message)):
        if "." not in candidate and ":" not in candidate:
            continue
        candidate = candidate.rstrip(".")
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            continue
    return ""


def _system_name(value: str) -> str:
    """Normalize legacy subscription contexts into a device identity."""

    system = _clean(value, 256)
    compatibility = re.fullmatch(
        r"notifinho[\s_-]*(.+?)[\s_-]*compat",
        system,
        re.IGNORECASE,
    )
    if compatibility:
        name = re.sub(
            r"(?<=[a-z0-9])(?=[A-Z])",
            " ",
            compatibility.group(1),
        )
        return _clean(name, 128).upper()
    return system


def _event_name(source: str, message_id: str, message: str) -> str:
    """Return a concise event label while retaining the full body message."""

    known = {
        ("dell_idrac", "USR0030"): "User Login",
        ("dell_idrac", "USR0031"): "Login Failed",
        ("dell_idrac", "USR0032"): "User Logout",
    }
    return known.get(
        (source, message_id.upper()),
        _clean(message or message_id or "Hardware event", 180),
    )


def _vendor(payload: dict, event: dict, hint: str = "") -> tuple[str, str]:
    normalized_hint = _clean(hint, 32).casefold()
    if normalized_hint in _VENDORS:
        item = _VENDORS[normalized_hint]
        return item["source"], item["name"]
    evidence = " ".join(
        (
            _clean(payload.get("Name")),
            _clean(event.get("MessageId")),
            _clean(event.get("MemberId")),
            _clean(json.dumps(event.get("Oem", {}), sort_keys=True)),
        )
    ).casefold()
    for key, item in _VENDORS.items():
        if any(marker in evidence for marker in item["markers"]):
            return item["source"], item["name"]
    return "redfish", "Redfish"


class RedfishParser:
    """Normalize standard Redfish Event Service payloads."""

    MAX_EVENTS = 64

    @classmethod
    def is_envelope(cls, payload) -> bool:
        if not isinstance(payload, dict):
            return False
        events = payload.get("Events")
        if not isinstance(events, list) or not 1 <= len(events) <= cls.MAX_EVENTS:
            return False
        return all(
            isinstance(event, dict)
            and bool(_clean(event.get("Message") or event.get("MessageId")))
            for event in events
        )

    def parse(self, payload: dict, vendor_hint: str = "") -> list[Notification]:
        if not self.is_envelope(payload):
            raise ValueError("invalid Redfish Event envelope")
        notifications = []
        for event in payload["Events"]:
            source, vendor_name = _vendor(payload, event, vendor_hint)
            system = _system_name(
                payload.get("Context") or event.get("Context"),
            )
            message_id = _clean(event.get("MessageId"), 256)
            registry = _clean(
                event.get("RegistryPrefix")
                or (message_id.split(".", 1)[0] if "." in message_id else ""),
                128,
            )
            message = _clean(event.get("Message") or message_id, 4000)
            severity = _clean(event.get("Severity"), 64)
            status, severity_label = _status(severity, message)
            origin = event.get("OriginOfCondition") or {}
            if not isinstance(origin, dict):
                origin = {}
            origin_path = _safe_origin(origin.get("@odata.id"))
            action = _clean(
                event.get("Resolution")
                or event.get("RecommendedAction"),
                1000,
            )
            event_id = _clean(
                event.get("EventId") or event.get("MemberId") or payload.get("Id"),
                256,
            )
            timestamp = _clean(
                event.get("EventTimestamp")
                or event.get("Created")
                or payload.get("EventTimestamp"),
                128,
            )
            fingerprint_source = "|".join(
                (
                    source,
                    system,
                    origin_path,
                    event_id,
                    message_id,
                    message,
                    timestamp,
                )
            )
            fingerprint = hashlib.sha256(
                fingerprint_source.encode("utf-8")
            ).hexdigest()
            item = Notification(
                source=source,
                category=_category(message_id, message, origin_path),
                status=status,
                title=_event_name(source, message_id, message),
                subject=message_id,
                body=message,
                start_time=timestamp,
            )
            item.metadata = {
                "provider": vendor_name,
                "vendor": vendor_name,
                "severity": severity_label,
                "system": system,
                "registry": registry,
                "message_id": message_id,
                "source_ip": _source_ip(message),
                "origin": origin_path,
                "recommended_action": action,
                "event_state": "resolved" if status == "success" else "active",
                "event_id": event_id,
                "deduplication_key": fingerprint,
                "parser_confidence": "high" if source != "redfish" else "medium",
                "format": "redfish-event-service",
            }
            notifications.append(item)
        return notifications


def _safe_origin(value) -> str:
    text = _clean(value, 1000)
    if not text:
        return ""
    parsed = urlsplit(text)
    if parsed.scheme or parsed.netloc:
        return parsed.path[:500]
    return text.split("?", 1)[0][:500]


class HardwareEmailParser:
    """Shared conservative parser for vendor hardware-management mail."""

    source = "redfish"
    vendor_name = "Hardware management"
    markers: tuple[str, ...] = ()

    @classmethod
    def is_message(cls, message: EmailMessage) -> bool:
        subject = _clean(message.get("Subject"), 500)
        sender = _clean(message.get("From"), 500)
        body = cls._body(message)
        evidence = f"{sender}\n{subject}\n{body}".casefold()
        brand = any(marker in evidence for marker in cls.markers)
        event = any(
            marker in evidence
            for marker in (
                "alertmail",
                "event log",
                "hardware",
                "integrated management log",
                "ipmi",
                "redfish",
                "sensor",
                "system event",
            )
        )
        return brand and event

    def parse(self, message: EmailMessage) -> Notification:
        if not self.is_message(message):
            raise ValueError(f"invalid {self.vendor_name} email")
        subject = _clean(message.get("Subject"), 500)
        body = self._body(message)
        fields = self._fields(body)
        event_message = fields.get("message") or fields.get("description") or body
        severity = fields.get("severity", "")
        status, severity_label = _status(severity, f"{subject}\n{event_message}")
        item = Notification(
            source=self.source,
            category=_category(subject, event_message, fields.get("sensor", "")),
            status=status,
            title=subject or f"{self.vendor_name} alert",
            subject=subject,
            body=_clean(event_message, 4000),
            sender=_clean(message.get("From"), 500),
            start_time=fields.get("event time", "") or fields.get("date", ""),
        )
        item.metadata = {
            "provider": self.vendor_name,
            "vendor": self.vendor_name,
            "severity": severity_label,
            "system": fields.get("system", "") or fields.get("host", ""),
            "sensor": fields.get("sensor", ""),
            "message_id": fields.get("message id", "") or fields.get("event id", ""),
            "recommended_action": fields.get("action", "") or fields.get("resolution", ""),
            "event_state": "resolved" if status == "success" else "active",
            "parser_confidence": "fixture-validated",
            "format": "smtp",
        }
        return item

    @staticmethod
    def _body(message: EmailMessage) -> str:
        plain = []
        html = []
        parts = message.walk() if message.is_multipart() else (message,)
        for part in parts:
            if part.get_content_disposition() == "attachment":
                continue
            content_type = part.get_content_type()
            if content_type not in {"text/plain", "text/html"}:
                continue
            try:
                payload = part.get_content()
            except Exception:
                raw = part.get_payload(decode=True) or b""
                payload = raw.decode(part.get_content_charset() or "utf-8", "replace")
            if content_type == "text/plain":
                plain.append(str(payload))
            else:
                html.append(BeautifulSoup(str(payload), "lxml").get_text("\n"))
        lines = []
        for line in "\n".join(plain or html).replace("\x00", " ").splitlines():
            cleaned = " ".join(line.split())
            if cleaned:
                lines.append(cleaned)
        return "\n".join(lines)[:12000]

    @staticmethod
    def _fields(body: str) -> dict[str, str]:
        fields = {}
        for match in re.finditer(
            r"(?im)^\s*(severity|system|host|sensor|message id|event id|"
            r"message|description|action|resolution|event time|date)\s*[:=-]\s*(.+)$",
            body,
        ):
            fields[match.group(1).casefold()] = _clean(match.group(2), 2000)
        return fields
