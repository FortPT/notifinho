"""Authenticated Home Assistant event contract and normalization."""

from __future__ import annotations

import re

from urllib.parse import urlsplit

from config import config
from models import Notification


class Parser:
    SCHEMA = "notifinho.home_assistant.v1"
    _ENTITY = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
    _ENDPOINT_PREFIX = re.compile(
        r"^\[(?P<device>[^\](]+)\((?P<host>[^)]+)\):(?P<port>\d+)\]\s*"
    )
    _IP_ENDPOINT = re.compile(
        r"(?<![\d.])(?P<host>(?:\d{1,3}\.){3}\d{1,3})"
        r"(?::(?P<port>\d{1,5}))?(?![\d.])"
    )
    _RETRY = re.compile(r"\bretrying\s+in\s+(?P<delay>\d+(?:\.\d+)?)\s*s\b", re.I)
    _ERROR_CODE = re.compile(
        r"\b(?P<name>[A-Z][A-Z0-9_]+)\((?P<number>-?\d+)\)"
    )
    _NAMED_ERROR = re.compile(
        r"\berror_code\s*=\s*(?P<name>[A-Z][A-Z0-9_]+)\b",
        re.I,
    )
    _ERRNO = re.compile(r"\[Errno\s+(?P<number>\d+)\]", re.I)
    _LONG_STATE = re.compile(
        r"State\s+.+?\s+for\s+(?P<entity>[a-z0-9_]+\.[a-z0-9_]+)\s+"
        r"is\s+longer\s+than\s+255,\s+falling\s+back\s+to\s+unknown",
        re.I,
    )
    _INVALID_STATE = re.compile(
        r"Value\s+error\s+while\s+updating\s+state\s+of\s+"
        r"(?P<entity>[a-z0-9_]+\.[a-z0-9_]+)",
        re.I,
    )
    _SERVICE_LABELS = {
        "cast": "Chromecast",
        "ipp": "Internet Printing Protocol",
        "kasa": "Tapo",
        "pychromecast": "Chromecast",
        "mqtt": "MQTT",
        "repairs": "Repairs",
        "update": "Updates",
        "system_log": "System log",
    }
    _SEVERITIES = {
        "information", "info", "success", "warning", "warn",
        "error", "critical", "fatal", "emergency",
    }
    _STATES = {
        "", "active", "firing", "pending", "resolved", "clear", "cleared",
        "ok", "success",
    }

    def __init__(self, aliases=None):
        self._aliases_override = aliases

    @classmethod
    def is_envelope(cls, payload) -> bool:
        if not isinstance(payload, dict):
            return False
        if payload.get("schema") != cls.SCHEMA:
            return False
        title = payload.get("title")
        message = cls._message(payload.get("message"))
        if not isinstance(title, str) or not title.strip() or len(title) > 256:
            return False
        if not message or len(message) > 4000:
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
        if not (
            isinstance(tags, list)
            and len(tags) <= 32
            and all(isinstance(tag, str) and 0 < len(tag.strip()) <= 64 for tag in tags)
        ):
            return False
        return all(
            not payload.get(name) or (
                isinstance(payload.get(name), str) and len(payload.get(name)) <= limit
            )
            for name, limit in {
                "component": 256,
                "service": 128,
                "event_type": 64,
            }.items()
        )

    def parse(self, payload: dict) -> Notification:
        if not self.is_envelope(payload):
            raise ValueError("invalid Home Assistant event envelope")

        raw_message = self._message(payload.get("message"))
        component = self._clean(
            payload.get("component") or payload.get("service"),
            256,
        )
        normalized = self._normalize_message(raw_message, component)
        aliases = self._aliases()
        profile = self._alias_profile(
            aliases,
            component,
            normalized["endpoint"],
        )
        endpoint = normalized["endpoint"] or profile["endpoint"]
        profile = self._alias_profile(aliases, component, endpoint)
        explicit_service = self._clean(payload.get("service"), 128)
        service = (
            explicit_service
            or profile["service"]
            or self._service_label(component, payload.get("category"))
        )
        endpoint = normalized["endpoint"] or profile["endpoint"]
        explicit_entity = self._clean(payload.get("entity_id"), 128)
        entity = explicit_entity or normalized["entity"]
        explicit_device = self._clean(payload.get("device"), 256)
        device = self._device_name(
            explicit_device,
            normalized["device"],
            profile["device"],
        )
        severity = self._clean(payload.get("severity") or "information", 32).casefold()
        status = self._status(payload.get("status"), severity)
        link = self._safe_link(payload.get("link"))
        title = self._title(
            self._clean(payload.get("title"), 256),
            service,
            device,
            entity,
            severity,
        )
        item = Notification(
            source="home_assistant",
            category=self._clean(payload.get("category") or "automation", 64).casefold(),
            status=status,
            title=title,
            subject=title,
            body=normalized["summary"],
            start_time=self._clean(payload.get("timestamp"), 128),
        )
        item.metadata = {
            "provider": "Home Assistant",
            "severity": severity,
            "service": service,
            "component": component,
            "event_type": self._clean(payload.get("event_type") or "automation", 64),
            "entity_id": entity,
            "device": device,
            "endpoint": endpoint,
            "error_code": normalized["error_code"],
            "retry_seconds": normalized["retry_seconds"],
            "area": self._clean(payload.get("area"), 256),
            "tags": [self._clean(tag, 64) for tag in payload.get("tags", [])],
            "action_link": link,
            "event_state": self._clean(payload.get("status") or status, 64),
            "parser_confidence": "high",
            "format": "home-assistant-v1",
        }
        return item

    @classmethod
    def _normalize_message(cls, value: str, component: str = "") -> dict[str, str]:
        text = cls._clean(value, 4000)
        text = re.sub(r"^Source:\s*.*?\s+-->\s*", "", text, flags=re.I)
        endpoint_match = cls._ENDPOINT_PREFIX.match(text)
        device = ""
        endpoint = ""
        if endpoint_match:
            device = cls._clean(endpoint_match.group("device"), 256)
            endpoint = cls._clean(
                f"{endpoint_match.group('host')}:{endpoint_match.group('port')}",
                256,
            )
            text = text[endpoint_match.end():].strip()

        if not endpoint:
            endpoint = cls._extract_endpoint(text)

        retry_match = cls._RETRY.search(text)
        retry_seconds = retry_match.group("delay") if retry_match else ""
        entity = ""

        long_state = cls._LONG_STATE.search(text)
        invalid_state = cls._INVALID_STATE.search(text)
        error_code = cls._extract_error_code(text)
        if long_state:
            entity = long_state.group("entity")
            summary = (
                f"State for {entity} exceeded Home Assistant's 255-character "
                "limit; the state was set to unknown."
            )
        elif invalid_state:
            entity = invalid_state.group("entity")
            summary = f"Home Assistant received an invalid state value for {entity}."
        elif cls._is_component(component, "ipp") and re.search(
            r"communicat(?:e|ing).+IPP\s+server",
            text,
            flags=re.I,
        ):
            summary = "Failed to communicate with the IPP server."
        elif cls._is_component(component, "kasa", "tplink"):
            module = cls._module_name(text)
            if re.search(r"error\s+processing", text, flags=re.I):
                summary = f"Failed to process the {module} module."
            else:
                summary = f"Failed to query the {module} module."
        elif re.search(r"error\s+reading\s+from\s+socket", text, flags=re.I):
            socket_error = re.sub(
                r"^.*?error\s+reading\s+from\s+socket\s*:\s*",
                "",
                text,
                flags=re.I,
            )
            socket_error = cls._ERRNO.sub("", socket_error).strip(" :,-")
            summary = cls._concise(socket_error or "Socket connection failed.", 320)
        else:
            summary = text
            service_info = re.search(r"\s+[A-Za-z0-9_]*ServiceInfo\s*\(", summary)
            if service_info:
                summary = summary[:service_info.start()].strip(" ,")
            if retry_match:
                summary = cls._RETRY.sub("", summary).strip(" ,.;")
            summary = cls._concise(summary, 320)

        return {
            "summary": summary or "Home Assistant reported an event.",
            "device": device,
            "endpoint": endpoint,
            "entity": entity,
            "retry_seconds": retry_seconds,
            "error_code": error_code,
        }

    def _aliases(self) -> dict:
        aliases = self._aliases_override
        if aliases is None:
            aliases = config.get("home_assistant", "aliases", default={})
        return aliases if isinstance(aliases, dict) else {}

    @classmethod
    def _alias_profile(cls, aliases, component: str, endpoint: str) -> dict[str, str]:
        profile = {"device": "", "endpoint": "", "service": ""}
        component_key = cls._clean(component, 256).casefold()
        endpoint_key = cls._clean(endpoint, 256).casefold()
        host_key = endpoint_key.rsplit(":", 1)[0] if endpoint_key else ""

        lookups = (
            (aliases.get("components"), component_key),
            (aliases.get("endpoints"), endpoint_key),
            (aliases.get("endpoints"), host_key),
        )
        for values, key in lookups:
            if not isinstance(values, dict) or not key:
                continue
            entry = next(
                (
                    value
                    for name, value in values.items()
                    if str(name).strip().casefold() == key
                ),
                None,
            )
            if not isinstance(entry, dict):
                continue
            for field, limit in (("device", 256), ("endpoint", 256), ("service", 128)):
                value = cls._clean(entry.get(field), limit)
                if value:
                    profile[field] = value
        return profile

    @classmethod
    def _extract_endpoint(cls, value: str) -> str:
        for match in cls._IP_ENDPOINT.finditer(value):
            host = match.group("host")
            if any(int(part) > 255 for part in host.split(".")):
                continue
            port = match.group("port") or ""
            if port and not 0 < int(port) <= 65535:
                continue
            return f"{host}:{port}" if port else host
        return ""

    @classmethod
    def _extract_error_code(cls, value: str) -> str:
        match = cls._ERROR_CODE.search(value)
        if match:
            return f"{match.group('name')} ({match.group('number')})"
        match = cls._NAMED_ERROR.search(value)
        if match:
            return match.group("name").upper()
        match = cls._ERRNO.search(value)
        if match:
            return f"Errno {match.group('number')}"
        return ""

    @classmethod
    def _module_name(cls, value: str) -> str:
        patterns = (
            r"modules?\s+['\"](?P<name>[A-Za-z0-9_ -]+)['\"]",
            r"module\s+query\s+['\"](?P<name>[A-Za-z0-9_ -]+)['\"]",
            r"error\s+processing\s+(?P<name>[A-Za-z0-9_ -]+?)\s+for\s+device",
        )
        for pattern in patterns:
            match = re.search(pattern, value, flags=re.I)
            if match:
                name = cls._clean(match.group("name"), 128)
                if name.casefold().startswith("get_"):
                    name = name[4:]
                if "_" in name:
                    name = "".join(part.title() for part in name.split("_") if part)
                return name or "device"
        return "device"

    @staticmethod
    def _is_component(component: str, *names: str) -> bool:
        value = str(component or "").casefold()
        parts = set(re.split(r"[.\s_-]+", value))
        return any(name.casefold() in parts for name in names)

    @classmethod
    def _service_label(cls, component, category) -> str:
        value = cls._clean(component, 256).casefold()
        for prefix in ("homeassistant.components.", "homeassistant."):
            if value.startswith(prefix):
                value = value[len(prefix):]
                break
        key = re.split(r"[.\s]", value, maxsplit=1)[0].replace("-", "_")
        if key in cls._SERVICE_LABELS:
            return cls._SERVICE_LABELS[key]
        if key:
            return key.replace("_", " ").title()
        fallback = cls._clean(category or "automation", 64).casefold()
        return cls._SERVICE_LABELS.get(fallback, fallback.replace("_", " ").title())

    @staticmethod
    def _device_name(explicit: str, detected: str, alias: str) -> str:
        if explicit and explicit.casefold() != "home assistant":
            return explicit
        return detected or alias

    @staticmethod
    def _title(title: str, service: str, device: str, entity: str, severity: str) -> str:
        normalized = title.casefold()
        generic = any(
            normalized.startswith(prefix)
            for prefix in (
                "home assistant event",
                "home assistant error",
                "home assistant warning",
            )
        )
        if not generic:
            return title
        subject = device or entity or service
        kind = "error" if severity in {"error", "critical", "fatal", "emergency"} else "event"
        return f"{subject} {kind}"[:256]

    @classmethod
    def _concise(cls, value, limit: int) -> str:
        text = cls._clean(value, 4000)
        if len(text) <= limit:
            return text
        candidate = text[:limit]
        sentence = max(candidate.rfind(". "), candidate.rfind("; "))
        if sentence >= 20:
            candidate = candidate[: sentence + 1]
        return candidate.rstrip(" ,.;:") + "…"

    @classmethod
    def _message(cls, value) -> str:
        if isinstance(value, str):
            return " ".join(value.replace("\x00", " ").split())
        if isinstance(value, (list, tuple)):
            selected = next((item for item in value if str(item or "").strip()), "")
            return " ".join(str(selected).replace("\x00", " ").split())
        return ""

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
