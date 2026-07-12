"""Shared, dependency-free helpers for private UniFi sample discovery."""

from __future__ import annotations

import re

from collections.abc import Iterable


REDACTED = "<redacted>"

_EMAIL_RE = re.compile(
    r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])",
    re.IGNORECASE,
)
_URL_RE = re.compile(
    r"\b(?:https?|wss?)://[^\s<>\"']+",
    re.IGNORECASE,
)
_UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
_MAC_RE = re.compile(
    r"\b(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b",
    re.IGNORECASE,
)
_IPV4_RE = re.compile(
    r"(?<![\d.])(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}(?![\d.])"
)
_IPV6_RE = re.compile(
    r"(?<![\w:])(?:[0-9a-f]{1,4}:){2,7}[0-9a-f]{0,4}(?![\w:])",
    re.IGNORECASE,
)
_INTERNAL_DOMAIN_RE = re.compile(
    r"\b(?:[a-z0-9-]+\.)+(?:internal|intranet|lan|local|home|corp|private)\b",
    re.IGNORECASE,
)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|token|cookie|set-cookie|webhook(?:_url)?)"
    r"(\s*[:=]\s*)([^\s,;]+)"
)
_BEARER_RE = re.compile(
    r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]+"
)
_SERIAL_RE = re.compile(
    r"(?i)\b(serial(?:[_ -]?number)?|device[_ -]?id|disk[_ -]?id)"
    r"(\s*[:=#-]?\s*)([A-Za-z0-9][A-Za-z0-9._:-]{5,})"
)
_LONG_IDENTIFIER_RE = re.compile(
    r"\b(?=[A-Za-z0-9_-]{16,}\b)(?=[A-Za-z0-9_-]*[A-Za-z])(?=[A-Za-z0-9_-]*\d)[A-Za-z0-9_-]+\b"
)


def sanitize_text(value: object) -> str:
    """Return a single-line representation with common private values hidden."""

    text = str(value).replace("\x00", "")
    text = _URL_RE.sub(REDACTED, text)
    text = _EMAIL_RE.sub(REDACTED, text)
    text = _UUID_RE.sub(REDACTED, text)
    text = _MAC_RE.sub(REDACTED, text)
    text = _IPV4_RE.sub(REDACTED, text)
    text = _IPV6_RE.sub(REDACTED, text)
    text = _INTERNAL_DOMAIN_RE.sub(REDACTED, text)
    text = _SECRET_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{REDACTED}",
        text,
    )
    text = _BEARER_RE.sub(REDACTED, text)
    text = _SERIAL_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{REDACTED}",
        text,
    )
    text = _LONG_IDENTIFIER_RE.sub(REDACTED, text)
    return " ".join(text.split())


def classify_unifi(values: Iterable[object]) -> list[str]:
    """Return deterministic likely application markers without parsing."""

    text = " ".join(str(value) for value in values).casefold()
    markers: list[str] = []

    categories = {
        "network": (
            "unifi network",
            "network application",
            "access point",
            "gateway",
            "switch",
            "wireless",
            "wifi",
        ),
        "protect": (
            "unifi protect",
            "protect application",
            "camera",
            "motion",
            "person detected",
            "vehicle detected",
            "doorbell",
        ),
        "drive": (
            "unifi drive",
            "drive application",
            "storage pool",
            "disk health",
            "backup job",
        ),
    }

    for category, needles in categories.items():

        if any(needle in text for needle in needles):
            markers.append(category)

    if not markers and ("unifi" in text or "ubiquiti" in text):
        markers.append("generic-unifi")

    if not markers:
        markers.append("unknown")

    return markers


def safe_header_names(names: Iterable[object]) -> list[str]:
    """Return only normalized, syntactically safe header names."""

    return sorted(
        {
            name
            for raw_name in names
            if (name := re.sub(r"[^A-Za-z0-9-]", "", str(raw_name)).lower())
        }
    )
