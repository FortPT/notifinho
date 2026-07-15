"""Shared presentation rules for Discord and Microsoft Teams cards."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any


class PresentationMixin:
    """Keep presentation, safety, and product branding consistent."""

    ICON_BASE_URL = (
        "https://raw.githubusercontent.com/FortPT/notifinho/"
        "main/assets/icons"
    )

    PRODUCT_ICONS = {
        "zabbix": "zabbix.png",
        "qnap": "qnap.png",
        "grafana": "grafana.png",
        "truenas": "truenas.png",
        "unifi": "unifi.png",
        "unifi_network": "unifi.png",
        "unifi_protect": "unifi.png",
        "unifi_drive": "unifi.png",
        "portainer": "portainer.png",
        "proxmox": "proxmox.png",
        "synology": "synology.png",
    }

    XO_ICON_URL = "https://content.vates.tech/assets/xologoname.png"

    _SECRET_ASSIGNMENT = re.compile(
        r"(?i)\b(authorization|api[_ -]?key|password|secret|session[_ -]?id|"
        r"token)\b(\s*[:=]\s*)([^\s,;)}\]]+)"
    )
    _BEARER_SECRET = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+")
    _DISCORD_WEBHOOK = re.compile(
        r"(?i)(https://(?:canary\.|ptb\.)?discord(?:app)?\.com/api/webhooks/)"
        r"[^\s/]+/[^\s)\]}]+"
    )
    _TOKEN_QUERY = re.compile(
        r"(?i)([?&](?:api[_-]?key|secret|token)=)[^&#\s]+"
    )

    def _sanitize_text(self, value: Any) -> str:
        """Remove credential material while retaining operational context."""

        text = "" if value is None else str(value).strip()
        text = self._BEARER_SECRET.sub("Bearer <redacted>", text)
        text = self._SECRET_ASSIGNMENT.sub(
            lambda match: f"{match.group(1)}{match.group(2)}<redacted>",
            text,
        )
        text = self._DISCORD_WEBHOOK.sub(r"\1<redacted>", text)
        return self._TOKEN_QUERY.sub(r"\1<redacted>", text)

    def _sanitize_payload(self, value: Any) -> Any:
        """Recursively remove credentials from an outbound card payload."""

        if isinstance(value, dict):
            return {
                key: self._sanitize_payload(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._sanitize_payload(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self._sanitize_payload(item) for item in value)
        if isinstance(value, str):
            return self._sanitize_text(value)
        return value

    def _truncate(self, value: Any, limit: int) -> str:
        text = self._sanitize_text(value)
        if len(text) <= limit:
            return text
        if limit <= 1:
            return text[:limit]
        return text[: limit - 1].rstrip() + "…"

    def _product_icon_url(self, source: str) -> str:
        normalized = str(source or "").strip().casefold()
        if normalized == "xo":
            return self.XO_ICON_URL
        filename = self.PRODUCT_ICONS.get(normalized)
        return f"{self.ICON_BASE_URL}/{filename}" if filename else ""

    def _set_discord_thumbnail(self, embed: dict, source: str) -> None:
        url = self._product_icon_url(source)
        if url:
            embed["thumbnail"] = {"url": url}

    def _teams_header(
        self,
        title: str,
        color: str,
        source: str,
    ) -> dict:
        """Return a title with a compact, top-right product icon."""

        title_block = {
            "type": "TextBlock",
            "text": self._truncate(title, 512),
            "weight": "Bolder",
            "size": "Large",
            "color": color,
            "wrap": True,
        }
        icon_url = self._product_icon_url(source)
        if not icon_url:
            return title_block
        return {
            "type": "ColumnSet",
            # Keep the legacy title metadata for downstream card tests and
            # integrations that inspect the JSON before Teams renders it.
            "text": title_block["text"],
            "color": color,
            "columns": [
                {
                    "type": "Column",
                    "width": "stretch",
                    "verticalContentAlignment": "Center",
                    "items": [title_block],
                },
                {
                    "type": "Column",
                    "width": "auto",
                    "verticalContentAlignment": "Center",
                    "items": [
                        {
                            "type": "Image",
                            "url": icon_url,
                            "altText": f"{source} icon",
                            "size": "Small",
                            "width": "48px",
                            "height": "48px",
                        }
                    ],
                },
            ],
        }

    def _format_datetime(self, value: Any) -> str:
        """Render timestamps as ``DD Mon YYYY • HH:MM [timezone]``."""

        if value is None or value == "":
            return ""

        if isinstance(value, datetime):
            parsed = value
            explicit_zone = parsed.tzinfo is not None
        else:
            raw = str(value).strip()
            if not raw:
                return ""

            if re.fullmatch(r"\d{10}(?:\.\d+)?", raw):
                parsed = datetime.fromtimestamp(float(raw), tz=timezone.utc)
                explicit_zone = True
            elif re.fullmatch(r"\d{13}", raw):
                parsed = datetime.fromtimestamp(int(raw) / 1000, tz=timezone.utc)
                explicit_zone = True
            else:
                parsed, explicit_zone = self._parse_datetime_text(raw)
                if parsed is None:
                    return self._sanitize_text(raw)

        suffix = ""
        if explicit_zone and parsed.tzinfo is not None:
            offset = parsed.utcoffset()
            if offset is not None:
                seconds = int(offset.total_seconds())
                if seconds == 0:
                    suffix = " UTC"
                else:
                    sign = "+" if seconds >= 0 else "-"
                    seconds = abs(seconds)
                    hours, remainder = divmod(seconds, 3600)
                    minutes = remainder // 60
                    suffix = f" UTC{sign}{hours:02d}:{minutes:02d}"

        return parsed.strftime("%d %b %Y • %H:%M") + suffix

    def _parse_datetime_text(self, value: str) -> tuple[datetime | None, bool]:
        cleaned = re.sub(r"(?<=\d)(?:st|nd|rd|th)\b", "", value)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        iso_value = cleaned
        if iso_value.endswith("Z"):
            iso_value = iso_value[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(iso_value)
            return parsed, parsed.tzinfo is not None
        except ValueError:
            pass

        formats = (
            "%A, %B %d %Y, %I:%M:%S %p",
            "%A, %B %d %Y, %I:%M %p",
            "%A, %b %d %Y, %I:%M:%S %p",
            "%A, %b %d %Y, %I:%M %p",
            "%B %d, %Y at %I:%M %p",
            "%B %d, %Y %I:%M %p",
            "%d %B %Y %H:%M:%S",
            "%d %B %Y %H:%M",
            "%d %b %Y • %H:%M:%S UTC",
            "%d %b %Y • %H:%M UTC",
            "%d %b %Y • %H:%M:%S",
            "%d %b %Y • %H:%M",
            "%d %b %Y %H:%M:%S UTC",
            "%d %b %Y %H:%M UTC",
            "%d/%m/%Y %H:%M:%S UTC",
            "%d/%m/%Y %H:%M UTC",
            "%d/%m/%y %H:%M:%S",
            "%d/%m/%y %H:%M",
            "%Y.%m.%d %H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
        )
        for fmt in formats:
            try:
                parsed = datetime.strptime(cleaned, fmt)
                if fmt.endswith(" UTC"):
                    parsed = parsed.replace(tzinfo=timezone.utc)
                    return parsed, True
                return parsed, False
            except ValueError:
                continue
        return None, False
