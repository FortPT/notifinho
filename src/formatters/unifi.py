"""Shared privacy and presentation helpers for UniFi formatters."""

from __future__ import annotations

import re

from datetime import datetime, timezone


_MAC_RE = re.compile(
    r"^(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}$",
    re.IGNORECASE,
)
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_PLACEHOLDER_MAC_RE = re.compile(
    r"(?:fake|placeholder|redacted)[ _-]*mac",
    re.IGNORECASE,
)
_OPAQUE_ALNUM_RE = re.compile(r"^[A-Za-z0-9]{16,}$")
_OPAQUE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{24,}$")


def protect_device_display(value) -> str:
    """Return only a human-readable Protect trigger-device value."""

    text = "" if value is None else str(value).strip()
    if not text:
        return ""
    if _MAC_RE.fullmatch(text) or _UUID_RE.fullmatch(text):
        return ""
    if _PLACEHOLDER_MAC_RE.search(text):
        return ""
    mixed_alphanumeric = any(character.isalpha() for character in text) and any(
        character.isdigit() for character in text
    )
    if mixed_alphanumeric and (
        _OPAQUE_ALNUM_RE.fullmatch(text)
        or _OPAQUE_TOKEN_RE.fullmatch(text)
    ):
        return ""
    return text


def format_protect_event_time(value) -> str:
    """Render seconds, milliseconds, or ISO values as UTC without fractions."""

    text = "" if value is None else str(value).strip()
    if not text:
        return ""
    try:
        if isinstance(value, (int, float)) or re.fullmatch(
            r"-?\d+(?:\.\d+)?",
            text,
        ):
            numeric = float(value)
            if abs(numeric) > 10_000_000_000:
                numeric /= 1000
            parsed = datetime.fromtimestamp(numeric, tz=timezone.utc)
        else:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            else:
                parsed = parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return text
    return parsed.strftime("%d/%m/%Y %H:%M:%S UTC")


def notification_status_icon(status, severity="") -> str:
    """Return one accessible Unicode status label for a UniFi title."""

    state = f"{status or ''} {severity or ''}".casefold()
    if "failure" in state or "critical" in state:
        return "🚨"
    if "warning" in state or "degraded" in state:
        return "⚠️"
    if "success" in state or "resolved" in state:
        return "✅"
    return "ℹ️"
