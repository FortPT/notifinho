"""Generic authenticated event-submission schema."""

from __future__ import annotations

import re

from urllib.parse import urlsplit

from models import Notification


class Parser:
    SCHEMA = "notifinho.event.v1"
    _SOURCE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
    _SEVERITIES = {
        "information", "info", "success", "warning", "warn",
        "error", "critical", "fatal", "emergency",
    }
    _STATES = {"", "active", "firing", "pending", "resolved", "clear", "cleared", "ok", "success"}

    @classmethod
    def is_envelope(cls, payload) -> bool:
        if not isinstance(payload, dict) or payload.get("schema") != cls.SCHEMA:
            return False
        source = payload.get("source")
        title = payload.get("title")
        message = payload.get("message")
        valid = bool(
            isinstance(source, str)
            and cls._SOURCE.fullmatch(source.strip())
            and isinstance(title, str)
            and title.strip()
            and len(title) <= 256
            and isinstance(message, str)
            and message.strip()
            and len(message) <= 4000
        )
        if not valid:
            return False
        severity = str(payload.get("severity") or "information").casefold()
        status = str(payload.get("status") or "").casefold()
        return severity in cls._SEVERITIES and status in cls._STATES

    def parse(self, payload: dict) -> Notification:
        if not self.is_envelope(payload):
            raise ValueError("invalid event submission envelope")
        source = payload["source"].strip().casefold()
        severity = self._clean(payload.get("severity") or "information", 32).casefold()
        status = self._status(payload.get("status"), severity)
        metadata = payload.get("metadata") or {}
        if not isinstance(metadata, dict) or len(metadata) > 32:
            raise ValueError("event metadata must be a bounded object")
        safe_metadata = {
            self._clean(key, 64): self._clean(value, 1000)
            for key, value in metadata.items()
            if isinstance(key, str) and isinstance(value, (str, int, float, bool))
        }
        safe_metadata.update(
            {
                "provider": self._clean(payload.get("provider") or source, 128),
                "severity": severity,
                "host": self._clean(payload.get("host"), 256),
                "event_state": self._clean(payload.get("status") or status, 64),
                "action_link": self._safe_link(payload.get("link")),
                "format": "event-api-v1",
            }
        )
        item = Notification(
            source=source,
            category=self._clean(payload.get("category") or "event", 64).casefold(),
            status=status,
            title=self._clean(payload.get("title"), 256),
            subject=self._clean(payload.get("title"), 256),
            body=self._clean(payload.get("message"), 4000),
            start_time=self._clean(payload.get("timestamp"), 128),
        )
        item.metadata = safe_metadata
        return item

    @staticmethod
    def _clean(value, limit: int) -> str:
        return " ".join(str(value or "").replace("\x00", " ").split())[:limit]

    @staticmethod
    def _status(value, severity: str) -> str:
        state = str(value or "").casefold()
        if state in {"resolved", "clear", "cleared", "ok", "success"}:
            return "success"
        if severity in {"error", "critical", "fatal", "emergency"}:
            return "failure"
        if severity in {"warning", "warn"}:
            return "warning"
        return "information"

    @staticmethod
    def _safe_link(value) -> str:
        text = str(value or "").strip()[:1000]
        parsed = urlsplit(text)
        if not text:
            return ""
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ""
        if parsed.username or parsed.password:
            return ""
        return text
