"""Shared, dependency-free helpers for private UniFi sample discovery."""

from __future__ import annotations

from collections.abc import Iterable

try:
    from scripts.discovery_safety import REDACTED, safe_header_names, sanitize_text
except ModuleNotFoundError:  # Direct execution from the scripts directory.
    from discovery_safety import (  # type: ignore[no-redef]
        REDACTED,
        safe_header_names,
        sanitize_text,
    )


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
