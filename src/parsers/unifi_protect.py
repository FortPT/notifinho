"""Parser for UniFi Protect Alarm Manager webhook envelopes."""

from __future__ import annotations

from urllib.parse import urlsplit

from config import config
from formatters.unifi import (
    humanize_unifi_identifier,
    protect_device_display,
)
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
        raw_trigger_device = self._text(primary.get("device"))
        trigger_device = self._resolve_device(
            raw_trigger_device,
            sources,
        )
        trigger_key = self._text(primary.get("key") or condition.get("source"))
        trigger_label = humanize_unifi_identifier(trigger_key)
        alarm_name = self._text(alarm.get("name")) or "UniFi Protect event"
        visible_title = trigger_label or alarm_name
        outer_time = self._timestamp(payload.get("timestamp"))
        event_time = self._timestamp(primary.get("timestamp")) or outer_time
        event_link = self._valid_url(alarm.get("eventLocalLink"))

        notification = Notification(
            source="unifi_protect",
            category="security",
            status="information",
            title=visible_title,
            subject=visible_title,
            body=self._body(trigger_label or trigger_key, trigger_device),
            start_time=event_time,
        )
        notification.items = normalized_triggers
        notification.metadata = {
            "provider": "UniFi Protect",
            "alarm_name": alarm_name,
            "condition_source": self._text(condition.get("source")),
            "condition_operator": self._text(condition.get("type")),
            "trigger_key": trigger_key,
            "trigger_label": trigger_label,
            "trigger_device": trigger_device,
            "trigger_device_id": raw_trigger_device,
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

    def _resolve_device(self, device, sources: list[dict]) -> str:
        """Resolve a Protect identifier without inventing a camera name."""

        raw = self._text(device)
        if not raw:
            return ""

        raw_key = self._device_key(raw)
        for source in sources:
            source_id = self._text(
                source.get("id")
                or source.get("deviceId")
                or source.get("device_id")
                or source.get("mac")
                or source.get("device")
            )
            friendly = self._text(
                source.get("name")
                or source.get("displayName")
                or source.get("display_name")
                or source.get("label")
            )
            if (
                source_id
                and self._device_key(source_id) == raw_key
                and protect_device_display(friendly)
            ):
                return friendly

        aliases = config.get(
            "notifications",
            "unifi_protect",
            "device_aliases",
            default={},
        )
        if isinstance(aliases, dict):
            for identifier, friendly in aliases.items():
                if self._device_key(identifier) != raw_key:
                    continue
                display = protect_device_display(friendly)
                if display:
                    return display

        return raw

    @staticmethod
    def _device_key(value) -> str:
        return "".join(
            character.casefold()
            for character in str(value or "")
            if character.isalnum()
        )

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
        """Validate and preserve the source epoch for presentation policy."""

        text = self._text(value)
        if not text:
            return ""
        try:
            float(text)
            return text
        except (TypeError, ValueError):
            return ""

    def _valid_url(self, value) -> str:
        text = self._text(value)
        try:
            parsed = urlsplit(text)
        except ValueError:
            return ""
        return text if parsed.scheme in {"http", "https"} and parsed.netloc else ""

    def _body(self, key, device) -> str:
        event = humanize_unifi_identifier(key) or "Event"
        target = protect_device_display(device)
        return f"{event} detected" + (f" by {target}" if target else "")

    def _text(self, value) -> str:
        return "" if value is None else str(value).strip()
