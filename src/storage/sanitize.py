"""Credential-safe text handling without importing runtime configuration."""

from __future__ import annotations

import re


_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(authorization|api[_ -]?key|password|secret|session[_ -]?id|"
    r"token)\b(\s*[:=]\s*)([^\s,;)}\]]+)"
)
_BEARER_SECRET = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+")
_DISCORD_WEBHOOK = re.compile(
    r"(?i)(https://(?:canary\.|ptb\.)?discord(?:app)?\.com/api/webhooks/)"
    r"[^\s/]+/[^\s)\]}]+"
)
_TOKEN_QUERY = re.compile(r"(?i)([?&](?:api[_-]?key|secret|token)=)[^&#\s]+")


def sanitize_text(value) -> str:
    text = "" if value is None else str(value).strip()
    text = _BEARER_SECRET.sub("Bearer <redacted>", text)
    text = _SECRET_ASSIGNMENT.sub(
        lambda match: f"{match.group(1)}{match.group(2)}<redacted>",
        text,
    )
    text = _DISCORD_WEBHOOK.sub(r"\1<redacted>", text)
    return _TOKEN_QUERY.sub(r"\1<redacted>", text)
