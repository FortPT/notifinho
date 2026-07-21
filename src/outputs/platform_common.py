"""Secret-safe payload, template, URL, and HTTP result helpers."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import re
import socket

from copy import deepcopy
from urllib.parse import urlsplit

import requests

from models import Notification
from storage.delivery import DeliveryResult
from storage.sanitize import sanitize_text


_SENSITIVE_KEY = re.compile(
    r"(?i)(authorization|cookie|password|secret|token|webhook|api[_-]?key)"
)
_PLACEHOLDER = re.compile(r"\$\{([a-z_][a-z0-9_]*)\}", re.IGNORECASE)


def notification_context(notification: Notification) -> dict[str, str]:
    metadata = notification.metadata or {}
    title = notification.title or notification.subject or "Notification"
    return {
        "body": sanitize_text(notification.body or title)[:4000],
        "category": sanitize_text(notification.category)[:128],
        "event_id": event_identifier(notification),
        "host": sanitize_text(
            metadata.get("host")
            or metadata.get("hostname")
            or metadata.get("device")
            or metadata.get("node")
        )[:256],
        "severity": sanitize_text(
            metadata.get("severity") or notification.status or "information"
        )[:64],
        "source": sanitize_text(notification.source)[:64],
        "status": sanitize_text(notification.status)[:64],
        "title": sanitize_text(title)[:512],
    }


def safe_event_envelope(notification: Notification) -> dict:
    context = notification_context(notification)
    metadata = _safe_json(notification.metadata or {}, depth=0)
    return {
        "schema": "notifinho.event.v1",
        "id": context["event_id"],
        "source": context["source"],
        "category": context["category"],
        "status": context["status"],
        "severity": context["severity"],
        "title": context["title"],
        "body": context["body"],
        "start_time": sanitize_text(notification.start_time)[:128],
        "end_time": sanitize_text(notification.end_time)[:128],
        "metadata": metadata,
    }


def event_identifier(notification: Notification) -> str:
    metadata = notification.metadata or {}
    supplied = metadata.get("event_id") or metadata.get("id")
    if supplied:
        normalized = re.sub(r"[^A-Za-z0-9._:-]", "-", str(supplied).strip())
        if normalized:
            return normalized[:128]
    seed = "\x1f".join(
        str(value or "")
        for value in (
            notification.source,
            notification.category,
            notification.status,
            notification.title or notification.subject,
            notification.start_time,
            notification.body,
        )
    )
    return hashlib.sha256(seed.encode("utf-8", errors="replace")).hexdigest()[:32]


def render_template(value, notification: Notification):
    context = notification_context(notification)

    def render(item):
        if isinstance(item, dict):
            return {str(key): render(child) for key, child in item.items()}
        if isinstance(item, list):
            return [render(child) for child in item]
        if isinstance(item, str):
            return _PLACEHOLDER.sub(
                lambda match: context.get(match.group(1).casefold(), ""),
                item,
            )
        return item

    return render(deepcopy(value))


def decode_secret(secret_value: bytes | None) -> dict:
    if secret_value is None:
        return {}
    try:
        text = secret_value.decode("utf-8").strip()
    except UnicodeDecodeError as error:
        raise ValueError("destination secret must be UTF-8") from error
    if not text:
        return {}
    if text.startswith("{"):
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError as error:
            raise ValueError("destination secret JSON is invalid") from error
        if not isinstance(decoded, dict):
            raise ValueError("destination secret JSON must be an object")
        return decoded
    return {"value": text}


def secret_url(secret_value: bytes | None) -> str:
    decoded = decode_secret(secret_value)
    return str(decoded.get("url") or decoded.get("value") or "").strip()


def validate_outbound_url(
    value: str,
    *,
    allow_private_network: bool = False,
    resolver=socket.getaddrinfo,
) -> str:
    text = str(value or "").strip()
    try:
        parsed = urlsplit(text)
    except ValueError as error:
        raise ValueError("destination URL is invalid") from error
    if (
        parsed.scheme.casefold() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValueError("destination URL must be credential-free HTTPS")
    if len(text) > 2048:
        raise ValueError("destination URL is too long")
    if not allow_private_network:
        try:
            addresses = {
                item[4][0]
                for item in resolver(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
            }
        except (OSError, socket.gaierror) as error:
            raise ValueError("destination hostname could not be resolved") from error
        if not addresses:
            raise ValueError("destination hostname could not be resolved")
        for address in addresses:
            ip = ipaddress.ip_address(address.split("%", 1)[0])
            if not ip.is_global:
                raise ValueError("destination resolves to a non-public address")
    return text


def validate_network_host(
    host: str,
    port: int,
    *,
    allow_private_network: bool = False,
    resolver=socket.getaddrinfo,
) -> None:
    if allow_private_network:
        return
    try:
        addresses = {
            item[4][0]
            for item in resolver(host, int(port), type=socket.SOCK_STREAM)
        }
    except (OSError, socket.gaierror) as error:
        raise ValueError("destination hostname could not be resolved") from error
    if not addresses:
        raise ValueError("destination hostname could not be resolved")
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
        if not ip.is_global:
            raise ValueError("destination resolves to a non-public address")


def safe_action_url(value) -> str:
    text = str(value or "").strip()
    try:
        parsed = urlsplit(text)
    except ValueError:
        return ""
    if (
        parsed.scheme.casefold() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or len(text) > 2048
    ):
        return ""
    return text


def http_delivery_result(response) -> DeliveryResult:
    status = int(response.status_code)
    if 200 <= status < 300:
        return DeliveryResult(True, response_status=status)
    retryable = status in {408, 409, 425, 429} or 500 <= status <= 599
    if status == 429:
        code = "rate_limited"
    elif 500 <= status <= 599:
        code = "upstream_unavailable"
    else:
        code = "upstream_rejected"
    return DeliveryResult(
        False,
        retryable=retryable,
        response_status=status,
        error_code=code,
        safe_error=f"destination returned HTTP {status}",
    )


def request_failure(error: Exception) -> DeliveryResult:
    retryable = isinstance(error, (requests.Timeout, requests.ConnectionError))
    return DeliveryResult(
        False,
        retryable=retryable,
        error_code="transport_unavailable" if retryable else "transport_error",
    )


def _safe_json(value, *, depth: int):
    if depth > 4:
        return "<omitted>"
    if isinstance(value, dict):
        safe = {}
        for key, item in list(value.items())[:64]:
            label = sanitize_text(key)[:128]
            if not label:
                continue
            if _SENSITIVE_KEY.search(label):
                safe[label] = "<redacted>"
            else:
                safe[label] = _safe_json(item, depth=depth + 1)
        return safe
    if isinstance(value, (list, tuple)):
        return [_safe_json(item, depth=depth + 1) for item in list(value)[:128]]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (int, float)):
        return value
    return sanitize_text(value)[:2000]
