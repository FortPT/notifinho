"""Validation helpers shared by persistent state services."""

from __future__ import annotations

import re
import unicodedata


_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")


def normalized_identifier(
    value: str,
    label: str,
    *,
    minimum: int = 1,
    maximum: int = 128,
) -> tuple[str, str]:
    display = unicodedata.normalize("NFKC", str(value or "")).strip()
    normalized = display.casefold()
    if not minimum <= len(display) <= maximum:
        raise ValueError(f"{label} must contain between {minimum} and {maximum} characters")
    if not _IDENTIFIER.fullmatch(normalized):
        raise ValueError(
            f"{label} must start with a letter or number and contain only "
            "letters, numbers, dot, underscore, or hyphen"
        )
    return display, normalized


def normalized_name(
    value: str,
    label: str,
    *,
    maximum: int = 128,
) -> tuple[str, str]:
    display = " ".join(unicodedata.normalize("NFKC", str(value or "")).split())
    if not 1 <= len(display) <= maximum:
        raise ValueError(f"{label} must contain between 1 and {maximum} characters")
    if any(unicodedata.category(character).startswith("C") for character in display):
        raise ValueError(f"{label} must not contain control characters")
    return display, display.casefold()
