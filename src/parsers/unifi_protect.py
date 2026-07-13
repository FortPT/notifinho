"""Parser for UniFi Protect Alarm Manager webhook envelopes."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlsplit

from models import Notification


class Parser:
    """Validate and normalize one Protect webhook."""

    @staticmethod
    def is_envelope(payload) -> bool:
        if not isinstance(payload, dict):
            return False
        alarm = payload.get("alarm")
        if not isinstance(alarm, dict):
            return False
        if "alarm_id" not in payload or "timestamp" not in payload:
            return False
        # Require the discovered nested shape, not generic alarm wording.
        return any(
            key in alarm
            for key in ("conditions", "sources", "triggers", "eventPath")
        ) and all(
            key not in alarm or isinstance(alarm.get(key), list)
            for key in ("conditions", "sources", "triggers")
        )

    def parse(self, payload: dict) -> Notification:
        if not self.is_envelope(payload):
            raise ValueError("invalid UniFi Protect webhook envelope")

        alarm = payload.get("alarm") or {}
        conditions = self._dict_members(alarm.get("conditions"))
        sources = self._dict_members(alarm.get("sources"))
        triggers = self._dict_members(alarm.get("triggers"))
        condition = self._condition(conditions)
        normalized_triggers = [self._trigger(item) for item in triggers]
        normalized_triggers = [item for item in normalized_triggers if item]
        primary = normalized_triggers[0] if normalized_triggers else {}
        trigger_key = self._text(primary.get("key") or condition.get("source"))
        alarm_name = self._text(alarm.get("name")) or "UniFi Protect event"
        outer_time = self._timestamp(payload.get("timestamp"))
        event_time = self._timestamp(primary.get("timestamp")) or outer_time
        event_link = self._valid_url(alarm.get("eventLocalLink"))

        notification = Notification(
            source="unifi_protect",
            category="security",
            status="information",
            title=alarm_name,
            subject=alarm_name,
            body=self._body(trigger_key, primary.get("device")),
            start_time=event_time,
        )
        notification.items = normalized_triggers
        notification.metadata = {
            "provider": "UniFi Protect",
            "alarm_name": alarm_name,
            "condition_source": self._text(condition.get("source")),
            "condition_operator": self._text(condition.get("type")),
            "trigger_key": trigger_key,
            "trigger_device": self._text(primary.get("device")),
            "trigger_timestamp": self._timestamp(primary.get("timestamp")),
            "outer_timestamp": outer_time,
            "event_time": event_time,
            "configured_source_count": len(sources),
            "trigger_count": len(normalized_triggers),
            "event_link": event_link,
            "event_path": self._text(alarm.get("eventPath")),
            "event_id": self._text(primary.get("event_id")),
            "alarm_id": self._text(payload.get("alarm_id")),
            "severity": "information",
            "parser_confidence": "high",
            "triggers": normalized_triggers,
        }
        return notification

    def _condition(self, members: list[dict]) -> dict:
        for member in members:
            condition = member.get("condition")
            if isinstance(condition, dict):
                return condition
        return {}

    def _trigger(self, member: dict) -> dict:
        if not isinstance(member, dict):
            return {}
        return {
            "key": self._text(member.get("key")),
            "device": self._text(member.get("device")),
            "timestamp": member.get("timestamp"),
            "event_id": self._text(member.get("eventId")),
        }

    def _dict_members(self, value) -> list[dict]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    def _timestamp(self, value) -> str:
        try:
            numeric = float(value)
            if numeric > 10_000_000_000:
                numeric /= 1000
            return datetime.fromtimestamp(numeric, tz=timezone.utc).isoformat()
        except (TypeError, ValueError, OSError, OverflowError):
            return ""

    def _valid_url(self, value) -> str:
        text = self._text(value)
        try:
            parsed = urlsplit(text)
        except ValueError:
            return ""
        return text if parsed.scheme in {"http", "https"} and parsed.netloc else ""

    def _body(self, key, device) -> str:
        event = self._text(key) or "event"
        target = self._text(device)
        return f"{event.title()} detected" + (f" by {target}" if target else "")

    def _text(self, value) -> str:
        return "" if value is None else str(value).strip()
