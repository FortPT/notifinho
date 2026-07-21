"""Validation and normalization for v2 platform destination settings."""

from __future__ import annotations

import json
import re

from urllib.parse import urlsplit


OUTPUT_TYPES = {"discord", "teams", "slack", "webhook", "mqtt", "ntfy"}
_HOST = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._:-]{0,251}[A-Za-z0-9])?$")
_HEADER = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]{1,64}$")
_FORBIDDEN_HEADERS = {
    "authorization",
    "connection",
    "content-length",
    "cookie",
    "host",
    "proxy-authorization",
    "te",
    "transfer-encoding",
    "upgrade",
}


def normalize_output_settings(
    output_type: str,
    settings: dict | None,
    *,
    require_complete: bool = False,
) -> dict:
    """Return bounded canonical settings or raise a non-secret validation error."""

    kind = str(output_type or "").strip().casefold()
    if kind not in OUTPUT_TYPES:
        raise ValueError("unsupported destination output type")
    if settings is None:
        settings = {}
    if not isinstance(settings, dict):
        raise ValueError("destination settings must be an object")

    validators = {
        "discord": _discord,
        "teams": _teams,
        "slack": _slack,
        "webhook": _webhook,
        "mqtt": _mqtt,
        "ntfy": _ntfy,
    }
    normalized = validators[kind](settings, require_complete)
    encoded = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    if len(encoded.encode("utf-8")) > 16 * 1024:
        raise ValueError("destination settings must not exceed 16384 bytes")
    return normalized


def validate_public_https_url(value, field: str) -> str:
    """Validate the structural, credential-free part of an outbound URL."""

    text = str(value or "").strip()
    try:
        parsed = urlsplit(text)
    except ValueError as error:
        raise ValueError(f"{field} must be a valid HTTPS URL") from error
    if (
        parsed.scheme.casefold() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValueError(f"{field} must be a credential-free HTTPS URL")
    if len(text) > 2048:
        raise ValueError(f"{field} must not exceed 2048 characters")
    return text


def _discord(settings, _complete):
    _unknown(settings, {"components_v2"})
    return {"components_v2": _boolean(settings, "components_v2", True)}


def _teams(settings, _complete):
    _unknown(settings, set())
    return {}


def _slack(settings, _complete):
    _unknown(settings, {"include_metadata"})
    return {"include_metadata": _boolean(settings, "include_metadata", True)}


def _webhook(settings, _complete):
    allowed = {
        "allow_private_network",
        "body_template",
        "headers",
        "method",
        "sign_hmac",
        "timeout_seconds",
    }
    _unknown(settings, allowed)
    method = str(settings.get("method", "POST")).strip().upper()
    if method not in {"POST", "PUT", "PATCH"}:
        raise ValueError("webhook method must be POST, PUT, or PATCH")
    headers = settings.get("headers", {})
    if not isinstance(headers, dict) or len(headers) > 32:
        raise ValueError("webhook headers must be an object with at most 32 entries")
    normalized_headers = {}
    for key, value in headers.items():
        name = str(key or "").strip()
        lowered = name.casefold()
        if not _HEADER.fullmatch(name) or lowered in _FORBIDDEN_HEADERS:
            raise ValueError(f"webhook header is not allowed: {name[:64]}")
        text = str(value or "").strip()
        if not text or "\r" in text or "\n" in text or len(text) > 512:
            raise ValueError(f"webhook header {name} has an invalid value")
        normalized_headers[name] = text
    template = settings.get("body_template")
    if template is not None:
        if not isinstance(template, dict):
            raise ValueError("webhook body_template must be an object")
        _bounded_template(template)
    result = {
        "method": method,
        "headers": normalized_headers,
        "timeout_seconds": _integer(settings, "timeout_seconds", 15, 1, 30),
        "sign_hmac": _boolean(settings, "sign_hmac", False),
        "allow_private_network": _boolean(
            settings,
            "allow_private_network",
            False,
        ),
    }
    if template is not None:
        result["body_template"] = template
    return result


def _mqtt(settings, complete):
    allowed = {
        "allow_private_network",
        "client_id",
        "host",
        "keepalive_seconds",
        "port",
        "qos",
        "retain",
        "tls",
        "topic",
    }
    _unknown(settings, allowed)
    host = str(settings.get("host") or "").strip()
    topic = str(settings.get("topic") or "").strip()
    if complete and not host:
        raise ValueError("mqtt host is required")
    if complete and not topic:
        raise ValueError("mqtt topic is required")
    if host and (len(host) > 253 or not _HOST.fullmatch(host)):
        raise ValueError("mqtt host is invalid")
    if topic and (len(topic.encode("utf-8")) > 256 or "\x00" in topic):
        raise ValueError("mqtt topic must not exceed 256 bytes")
    if "#" in topic or "+" in topic:
        raise ValueError("mqtt publish topic must not contain wildcards")
    tls = _boolean(settings, "tls", True)
    client_id = str(settings.get("client_id") or "").strip()
    if len(client_id) > 128:
        raise ValueError("mqtt client_id must not exceed 128 characters")
    result = {
        "host": host,
        "port": _integer(settings, "port", 8883 if tls else 1883, 1, 65535),
        "topic": topic,
        "qos": _integer(settings, "qos", 1, 0, 2),
        "retain": _boolean(settings, "retain", False),
        "tls": tls,
        "keepalive_seconds": _integer(
            settings,
            "keepalive_seconds",
            60,
            10,
            300,
        ),
        "allow_private_network": _boolean(
            settings,
            "allow_private_network",
            False,
        ),
    }
    if client_id:
        result["client_id"] = client_id
    return result


def _ntfy(settings, complete):
    allowed = {
        "allow_private_network",
        "include_action",
        "priority",
        "server",
        "tags",
        "timeout_seconds",
        "title",
        "topic",
    }
    _unknown(settings, allowed)
    server = str(settings.get("server") or "").strip()
    topic = str(settings.get("topic") or "").strip()
    if complete and not server:
        raise ValueError("ntfy server is required")
    if complete and not topic:
        raise ValueError("ntfy topic is required")
    if server:
        server = validate_public_https_url(server, "ntfy server").rstrip("/")
    if topic and (
        len(topic) > 128
        or not re.fullmatch(r"[A-Za-z0-9_-]+", topic)
    ):
        raise ValueError("ntfy topic must use letters, numbers, underscore, or hyphen")
    priority = settings.get("priority", "default")
    if isinstance(priority, int) and not isinstance(priority, bool):
        if not 1 <= priority <= 5:
            raise ValueError("ntfy priority must be between 1 and 5")
    else:
        priority = str(priority or "default").strip().casefold()
        if priority not in {"min", "low", "default", "high", "max"}:
            raise ValueError("ntfy priority is invalid")
    tags = settings.get("tags", [])
    if not isinstance(tags, list) or len(tags) > 12:
        raise ValueError("ntfy tags must be a list with at most 12 entries")
    normalized_tags = []
    for tag in tags:
        text = str(tag or "").strip()
        if not text or len(text) > 32 or not re.fullmatch(r"[A-Za-z0-9_+-]+", text):
            raise ValueError("ntfy tags contain an invalid value")
        if text not in normalized_tags:
            normalized_tags.append(text)
    title = str(settings.get("title") or "${title}").strip()
    if not title or len(title) > 256:
        raise ValueError("ntfy title must contain 1 to 256 characters")
    return {
        "server": server,
        "topic": topic,
        "priority": priority,
        "tags": normalized_tags,
        "title": title,
        "include_action": _boolean(settings, "include_action", True),
        "timeout_seconds": _integer(settings, "timeout_seconds", 15, 1, 30),
        "allow_private_network": _boolean(
            settings,
            "allow_private_network",
            False,
        ),
    }


def _unknown(settings, allowed):
    unknown = sorted(str(key) for key in set(settings) - allowed)
    if unknown:
        raise ValueError(f"unsupported destination setting: {unknown[0]}")


def _boolean(settings, key, default):
    value = settings.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"destination setting {key} must be true or false")
    return value


def _integer(settings, key, default, minimum, maximum):
    value = settings.get(key, default)
    if isinstance(value, bool):
        raise ValueError(f"destination setting {key} must be an integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"destination setting {key} must be an integer") from error
    if not minimum <= number <= maximum:
        raise ValueError(
            f"destination setting {key} must be between {minimum} and {maximum}"
        )
    return number


def _bounded_template(value, depth=0):
    if depth > 6:
        raise ValueError("webhook body_template must not exceed six levels")
    if isinstance(value, dict):
        if len(value) > 64:
            raise ValueError("webhook body_template contains too many keys")
        for key, item in value.items():
            if not str(key) or len(str(key)) > 128:
                raise ValueError("webhook body_template contains an invalid key")
            _bounded_template(item, depth + 1)
    elif isinstance(value, list):
        if len(value) > 128:
            raise ValueError("webhook body_template contains too many items")
        for item in value:
            _bounded_template(item, depth + 1)
    elif isinstance(value, str):
        if len(value) > 4096:
            raise ValueError("webhook body_template text is too long")
    elif value is not None and not isinstance(value, (bool, int, float)):
        raise ValueError("webhook body_template must contain JSON values")
