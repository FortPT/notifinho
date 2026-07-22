"""Formal, dependency-free v1.9 configuration and event validation."""

from __future__ import annotations

import ipaddress
import os
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from copy import deepcopy
from urllib.parse import urlsplit


_SECRET_KEY = re.compile(
    r"(?i)(authorization|api[_-]?key|password|secret|token|webhook)"
)


def mask_secrets(value):
    if isinstance(value, dict):
        masked = {}
        for key, item in value.items():
            if (
                _SECRET_KEY.search(str(key))
                and not isinstance(item, (dict, list))
                and item not in (None, "", False)
            ):
                masked[key] = "<configured>"
            else:
                masked[key] = mask_secrets(item)
        return masked
    if isinstance(value, list):
        return [mask_secrets(item) for item in value]
    return deepcopy(value)


def merge_masked_secrets(current, proposed):
    """Preserve existing secret leaves represented by the API placeholder."""

    if proposed == "<configured>":
        if current in (None, "", False) or isinstance(current, (dict, list)):
            raise ValueError("configured secret placeholder has no existing value")
        return deepcopy(current)
    if isinstance(proposed, dict):
        previous = current if isinstance(current, dict) else {}
        return {
            key: merge_masked_secrets(previous.get(key), value)
            for key, value in proposed.items()
        }
    if isinstance(proposed, list):
        previous = current if isinstance(current, list) else []
        return [
            merge_masked_secrets(
                previous[index] if index < len(previous) else None,
                value,
            )
            for index, value in enumerate(proposed)
        ]
    return deepcopy(proposed)


def validate_config(data) -> list[str]:
    errors = []
    if not isinstance(data, dict):
        return ["configuration must be an object"]
    for section in (
        "smtp",
        "http",
        "outputs",
        "routing",
        "notifications",
        "presentation",
        "api",
        "platform",
        "webui",
    ):
        if section in data and not isinstance(data[section], dict):
            errors.append(f"{section} must be an object")
    http = data.get("http") or {}
    if "port" in http and not _port(http.get("port")):
        errors.append("http.port must be between 1 and 65535")
    if "max_body_bytes" in http and not _integer_range(
        http.get("max_body_bytes"), 1, 16 * 1024 * 1024
    ):
        errors.append("http.max_body_bytes must be between 1 and 16777216")
    presentation = data.get("presentation") or {}
    if isinstance(presentation, dict) and "timezone" in presentation:
        zone_name = str(presentation.get("timezone") or "").strip()
        try:
            if not zone_name:
                raise ZoneInfoNotFoundError
            ZoneInfo(zone_name)
        except (ZoneInfoNotFoundError, ValueError):
            errors.append(
                "presentation.timezone must be a valid IANA timezone"
            )
    api = data.get("api") or {}
    platform = data.get("platform") or {}
    webui = data.get("webui") or {}
    if isinstance(webui, dict):
        if "enabled" in webui and not isinstance(webui.get("enabled"), bool):
            errors.append("webui.enabled must be a boolean")
    if isinstance(platform, dict):
        if "enabled" in platform and not isinstance(platform.get("enabled"), bool):
            errors.append("platform.enabled must be a boolean")
        if "secure_cookies" in platform and not isinstance(
            platform.get("secure_cookies"),
            bool,
        ):
            errors.append("platform.secure_cookies must be a boolean")
        if "state_dir" in platform:
            state_dir = str(platform.get("state_dir") or "").strip()
            if not os.path.isabs(state_dir) or state_dir == os.path.sep:
                errors.append(
                    "platform.state_dir must be an absolute directory other than /"
                )
    tokens = api.get("tokens") or {}
    if not isinstance(tokens, dict):
        errors.append("api.tokens must be an object")
        tokens = {}
    for name, settings in tokens.items():
        prefix = f"api.tokens.{name}"
        if not isinstance(settings, dict):
            errors.append(f"{prefix} must be an object")
            continue
        if "token" in settings:
            errors.append(f"{prefix}.token is not allowed; use env, file, or SHA-256")
        configured = [
            bool(settings.get("token_env")),
            bool(settings.get("token_file")),
            bool(settings.get("token_sha256")),
        ]
        if settings.get("enabled", True) and sum(configured) != 1:
            errors.append(f"{prefix} must configure exactly one token source")
        token_hash = str(settings.get("token_sha256") or "")
        if token_hash and not re.fullmatch(r"[0-9a-fA-F]{64}", token_hash):
            errors.append(f"{prefix}.token_sha256 must be 64 hexadecimal characters")
        role = str(settings.get("role") or "application").casefold()
        if role not in {"admin", "application"}:
            errors.append(f"{prefix}.role must be admin or application")
        sources = settings.get("sources") or []
        if isinstance(sources, str):
            sources = [sources]
        if not isinstance(sources, list) or not all(
            isinstance(source, str) and source.strip() for source in sources
        ):
            errors.append(f"{prefix}.sources must be a list of source names")
        if "rate_limit_per_minute" in settings and not _integer_range(
            settings.get("rate_limit_per_minute"), 1, 10_000
        ):
            errors.append(f"{prefix}.rate_limit_per_minute must be between 1 and 10000")
    routing = data.get("routing") or {}
    notifications = data.get("notifications") or {}
    if isinstance(notifications, dict) and "dell_idrac" in notifications:
        dell_idrac = notifications.get("dell_idrac")
        if not isinstance(dell_idrac, dict):
            errors.append("notifications.dell_idrac must be an object")
        else:
            trusted = dell_idrac.get(
                "suppress_ipmi_session_audit_from",
                [],
            )
            if not isinstance(trusted, list):
                errors.append(
                    "notifications.dell_idrac."
                    "suppress_ipmi_session_audit_from must be a list"
                )
            else:
                for index, value in enumerate(trusted):
                    try:
                        ipaddress.ip_address(str(value).strip())
                    except ValueError:
                        errors.append(
                            "notifications.dell_idrac."
                            "suppress_ipmi_session_audit_from."
                            f"{index} must be an IP address"
                        )
    outputs = data.get("outputs") or {}
    if isinstance(outputs, dict):
        for output_name, settings in outputs.items():
            if not isinstance(settings, dict):
                errors.append(f"outputs.{output_name} must be an object")
                continue
            if "enabled" in settings and not isinstance(
                settings.get("enabled"),
                bool,
            ):
                errors.append(f"outputs.{output_name}.enabled must be a boolean")
    if isinstance(routing, dict):
        for source, route in routing.items():
            if not isinstance(route, dict):
                errors.append(f"routing.{source} must be an object")
                continue
            destinations = route.get("outputs", [route])
            if not isinstance(destinations, list) or not destinations:
                errors.append(f"routing.{source}.outputs must be a non-empty list")
                continue
            for index, destination in enumerate(destinations):
                prefix = f"routing.{source}.outputs.{index}"
                if not isinstance(destination, dict):
                    errors.append(f"{prefix} must be an object")
                    continue
                output = str(destination.get("output") or "").strip()
                target = str(destination.get("target") or "").strip()
                if output not in {"discord", "teams"}:
                    errors.append(f"{prefix}.output must be discord or teams")
                    continue
                if not target:
                    errors.append(f"{prefix}.target is required")
                    continue
                settings = outputs.get(output) if isinstance(outputs, dict) else None
                target_settings = settings.get(target) if isinstance(settings, dict) else None
                if not isinstance(target_settings, dict):
                    errors.append(f"{prefix} references missing {output}.{target}")
                elif not str(target_settings.get("webhook") or "").strip():
                    errors.append(f"outputs.{output}.{target}.webhook is required")
                elif output == "teams" and not _valid_https_url(
                    target_settings.get("webhook")
                ):
                    errors.append(
                        f"outputs.teams.{target}.webhook must be a valid HTTPS URL"
                    )
    return errors


def _port(value) -> bool:
    return _integer_range(value, 1, 65535)


def _integer_range(value, minimum: int, maximum: int) -> bool:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return False
    return minimum <= number <= maximum


def _valid_https_url(value) -> bool:
    text = str(value or "").strip()
    lowered = text.casefold()
    if not text or "paste_here" in lowered or text == "<configured>":
        return False
    try:
        parsed = urlsplit(text)
        return (
            parsed.scheme.casefold() == "https"
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
        )
    except ValueError:
        return False
