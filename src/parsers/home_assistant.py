"""Authenticated Home Assistant automation-event contract."""

from __future__ import annotations

import re

from urllib.parse import urlsplit

from models import Notification


class Parser:
    SCHEMA = "notifinho.home_assistant.v1"
    _ENTITY = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
    _SEVERITIES = {
        "information", "info", "success", "warning", "warn",
        "error", "critical", "fatal", "emergency",
    }
    _STATES = {"", "active", "firing", "pending", "resolved", "clear", "cleared", "ok", "success"}

    @classmethod
    def is_envelope(cls, payload) -> bool:
        if not isinstance(payload, dict):
            return False
        if payload.get("schema") != cls.SCHEMA:
            return False
        title = payload.get("title")
        message = payload.get("message")
        if not isinstance(title, str) or not title.strip() or len(title) > 256:
            return False
        if not isinstance(message, str) or not message.strip() or len(message) > 4000:
            return False
        severity = str(payload.get("severity") or "information").casefold()
        status = str(payload.get("status") or "").casefold()
        if severity not in cls._SEVERITIES or status not in cls._STATES:
            return False
        entity = payload.get("entity_id", "")
        if entity and (
            not isinstance(entity, str) or not cls._ENTITY.fullmatch(entity.strip())
        ):
            return False
        tags = payload.get("tags", [])
        return isinstance(tags, list) and len(tags) <= 32 and all(
            isinstance(tag, str) and 0 < len(tag.strip()) <= 64 for tag in tags
        )

    def parse(self, payload: dict) -> Notification:
        if not self.is_envelope(payload):
            raise ValueError("invalid Home Assistant event envelope")
        severity = self._clean(payload.get("severity") or "information", 32).casefold()
        status = self._status(payload.get("status"), severity)
        link = self._safe_link(payload.get("link"))
        item = Notification(
            source="home_assistant",
            category=self._clean(payload.get("category") or "automation", 64).casefold(),
            status=status,
            title=self._clean(payload.get("title"), 256),
            subject=self._clean(payload.get("title"), 256),
            body=self._clean(payload.get("message"), 4000),
            start_time=self._clean(payload.get("timestamp"), 128),
        )
        item.metadata = {
            "provider": "Home Assistant",
            "severity": severity,
            "entity_id": self._clean(payload.get("entity_id"), 128),
            "device": self._clean(payload.get("device"), 256),
            "area": self._clean(payload.get("area"), 256),
            "tags": [self._clean(tag, 64) for tag in payload.get("tags", [])],
            "action_link": link,
            "event_state": self._clean(payload.get("status") or status, 64),
            "parser_confidence": "high",
            "format": "home-assistant-v1",
        }
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
        if not text:
            return ""
        parsed = urlsplit(text)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ""
        if parsed.username or parsed.password:
            return ""
        return text
