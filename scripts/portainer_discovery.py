"""Shared, dependency-free helpers for private Portainer sample discovery."""

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


def classify_portainer(values: Iterable[object]) -> list[str]:
    """Return deterministic discovery markers without claiming parser support."""

    text = " ".join(str(value) for value in values).casefold()
    markers: list[str] = []

    if "portainer" in text:
        markers.append("portainer")

    alert_fields = (
        "alert name",
        "started at",
        "last updated",
        "severity",
        "instance",
    )
    if sum(field in text for field in alert_fields) >= 3:
        markers.append("alerting-envelope")

    if "alertmanager" in text or "status" in text and "alerts" in text:
        markers.append("alertmanager-compatible")

    if not markers:
        markers.append("unknown")

    return markers


__all__ = [
    "REDACTED",
    "classify_portainer",
    "safe_header_names",
    "sanitize_text",
]
