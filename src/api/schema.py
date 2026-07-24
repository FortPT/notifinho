"""Formal, dependency-free v1.9 configuration and event validation."""

from __future__ import annotations

import ipaddress
import os
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from copy import deepcopy
from urllib.parse import urlsplit

from outputs.settings import OUTPUT_TYPES, normalize_output_settings


_SECRET_KEY = re.compile(
    r"(?i)(authorization|api[_-]?key|password|secret|token|webhook)"
)


def mask_secrets(value, sensitive=False):
    if isinstance(value, dict):
        masked = {}
        for key, item in value.items():
            direct = bool(_SECRET_KEY.search(str(key)))
            inherited = sensitive or (
                direct
                and isinstance(item, (dict, list))
                and str(key).casefold()
                in {"secret", "credential", "credentials", "authentication"}
            )
            masked[key] = mask_secrets(
                item,
                sensitive=inherited or (direct and not isinstance(item, (dict, list))),
            )
        return masked
    if isinstance(value, list):
        return [mask_secrets(item, sensitive=sensitive) for item in value]
    if sensitive and value not in (None, "", False):
        return "<configured>"
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
    if isinstance(presentation, dict) and "time_format" in presentation:
        if str(presentation.get("time_format")) not in {"12", "24"}:
            errors.append("presentation.time_format must be 12 or 24")
    api = data.get("api") or {}
    platform = data.get("platform") or {}
    webui = data.get("webui") or {}
    if isinstance(webui, dict):
        if "enabled" in webui and not isinstance(webui.get("enabled"), bool):
            errors.append("webui.enabled must be a boolean")
        if "enforce_https" in webui and not isinstance(
            webui.get("enforce_https"), bool
        ):
            errors.append("webui.enforce_https must be a boolean")
        if "language" in webui and webui.get("language") not in {"en-GB", "pt-PT"}:
            errors.append("webui.language must be en-GB or pt-PT")
        source_categories = webui.get("source_categories", {})
        if not isinstance(source_categories, dict):
            errors.append("webui.source_categories must be an object")
        else:
            allowed_categories = {
                "servers", "services", "applications", "controllers",
                "virtualization", "monitoring", "storage", "networking",
                "hardware", "automation", "containers", "security", "generic",
            }
            for source, category in source_categories.items():
                if not re.fullmatch(
                    r"[a-z0-9][a-z0-9_.-]{0,79}",
                    str(source or "").strip().casefold(),
                ):
                    errors.append("webui.source_categories contains an invalid source")
                    break
                if str(category or "").strip().casefold() not in allowed_categories:
                    errors.append("webui.source_categories contains an invalid category")
                    break
        removed_sources = webui.get("removed_sources", [])
        if not isinstance(removed_sources, list) or not all(
            re.fullmatch(
                r"[a-z0-9][a-z0-9_.-]{0,79}",
                str(source or "").strip().casefold(),
            )
            for source in removed_sources
        ):
            errors.append("webui.removed_sources must be a list of source names")
        public_url = str(webui.get("public_url") or "").strip()
        if public_url and not re.fullmatch(r"https://[^/\s]+(?:/[^\s]*)?", public_url):
            errors.append("webui.public_url must be an HTTPS URL")
    if isinstance(platform, dict):
        if "enabled" in platform and not isinstance(platform.get("enabled"), bool):
            errors.append("platform.enabled must be a boolean")
        if "secure_cookies" in platform and not isinstance(
            platform.get("secure_cookies"),
            bool,
        ):
            errors.append("platform.secure_cookies must be a boolean")
        if "routing_authority" in platform:
            authority = str(platform.get("routing_authority") or "").casefold()
            if authority not in {"yaml", "database"}:
                errors.append(
                    "platform.routing_authority must be yaml or database"
                )
        if "configuration_model" in platform and platform.get("configuration_model") not in {
            "unified_yaml_v1",
            "platform_database_v1",
        }:
            errors.append(
                "platform.configuration_model must be unified_yaml_v1 or platform_database_v1"
            )
        if platform.get("configuration_model") == "platform_database_v1":
            moved_sections = {
                "outputs": "destinations",
                "routing": "routes",
                "notifications": "integration settings",
                "presentation": "regional settings",
                "home_assistant": "Home Assistant aliases",
                "redfish": "Redfish settings",
            }
            for section, resource in moved_sections.items():
                if section in data:
                    errors.append(
                        f"{section} is database-managed; edit {resource} in the WebUI"
                    )
            if isinstance(api, dict) and "tokens" in api:
                errors.append("api.tokens is database-managed; edit applications in the WebUI")
            if "backups" in platform:
                errors.append(
                    "platform.backups is database-managed; edit backup settings in the WebUI"
                )
            if isinstance(webui, dict) and "language" in webui:
                errors.append(
                    "webui.language is database-managed; edit regional settings in the WebUI"
                )
        if "backup_retention" in platform:
            retention = platform.get("backup_retention")
            if (
                isinstance(retention, bool)
                or not isinstance(retention, int)
                or not 1 <= retention <= 100
            ):
                errors.append(
                    "platform.backup_retention must be between 1 and 100"
                )
        if "state_dir" in platform:
            state_dir = str(platform.get("state_dir") or "").strip()
            if not os.path.isabs(state_dir) or state_dir == os.path.sep:
                errors.append(
                    "platform.state_dir must be an absolute directory other than /"
                )
        backups = platform.get("backups")
        if backups is not None:
            if not isinstance(backups, dict):
                errors.append("platform.backups must be an object")
            else:
                schedule = str(backups.get("schedule") or "disabled").casefold()
                if schedule not in {"disabled", "daily", "weekly", "monthly"}:
                    errors.append("platform.backups.schedule is invalid")
                if not re.fullmatch(
                    r"(?:[01][0-9]|2[0-3]):[0-5][0-9]",
                    str(backups.get("time") or "02:00"),
                ):
                    errors.append("platform.backups.time must use HH:MM")
                if not _integer_range(backups.get("weekday", 0), 0, 6):
                    errors.append("platform.backups.weekday must be between 0 and 6")
                if not _integer_range(backups.get("day", 1), 1, 28):
                    errors.append("platform.backups.day must be between 1 and 28")
                target_id = str(backups.get("target_id") or "")
                if target_id and not re.fullmatch(r"[0-9a-f]{32}", target_id):
                    errors.append("platform.backups.target_id is invalid")
                if not isinstance(backups.get("managed_mounts", False), bool):
                    errors.append("platform.backups.managed_mounts must be a boolean")
                external_enabled = backups.get("external_enabled", False)
                if not isinstance(external_enabled, bool):
                    errors.append("platform.backups.external_enabled must be a boolean")
                if str(backups.get("external_type") or "nfs").casefold() not in {"nfs", "smb"}:
                    errors.append("platform.backups.external_type must be nfs or smb")
                external_path = str(backups.get("external_path") or "").strip()
                if external_enabled and (
                    not os.path.isabs(external_path) or external_path == os.path.sep
                ):
                    errors.append(
                        "platform.backups.external_path must be an absolute mounted directory other than /"
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
        destination_names = set()
        for output_name, settings in outputs.items():
            if not isinstance(settings, dict):
                errors.append(f"outputs.{output_name} must be an object")
                continue
            if output_name not in OUTPUT_TYPES:
                errors.append(f"outputs.{output_name} is not a supported output type")
                continue
            if "enabled" in settings and not isinstance(
                settings.get("enabled"),
                bool,
            ):
                errors.append(f"outputs.{output_name}.enabled must be a boolean")
            for target, destination in settings.items():
                if target == "enabled":
                    continue
                prefix = f"outputs.{output_name}.{target}"
                if not isinstance(destination, dict):
                    errors.append(f"{prefix} must be an object")
                    continue
                display_name = " ".join(
                    str(destination.get("name") or target).split()
                ).casefold()
                if display_name in destination_names:
                    errors.append(
                        f"{prefix}.name duplicates another destination name"
                    )
                destination_names.add(display_name)
                if "enabled" in destination and not isinstance(destination.get("enabled"), bool):
                    errors.append(f"{prefix}.enabled must be a boolean")
                public_settings = destination.get("settings")
                if public_settings is None:
                    public_settings = {
                        key: value
                        for key, value in destination.items()
                        if key not in {"enabled", "name", "settings", "shared", "secret", "webhook"}
                    }
                try:
                    normalize_output_settings(output_name, public_settings or {})
                except (TypeError, ValueError) as error:
                    errors.append(f"{prefix}: {error}")
                configured_secret = destination.get("secret")
                if configured_secret is None:
                    configured_secret = destination.get("webhook")
                destination_enabled = (
                    settings.get("enabled", True) is True
                    and destination.get("enabled", True) is True
                )
                if output_name == "teams":
                    if destination_enabled and configured_secret in (None, "", {}):
                        errors.append(f"{prefix}.webhook is required")
                    elif configured_secret not in (None, "", {}) and not _valid_https_url(configured_secret):
                        errors.append(f"{prefix}.webhook must be a valid HTTPS URL")
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
                input_type = str(destination.get("input") or "").strip().casefold()
                if input_type and input_type not in {"smtp", "http", "redfish"}:
                    errors.append(f"{prefix}.input must be smtp, http, or redfish")
                if output not in OUTPUT_TYPES:
                    errors.append(f"{prefix}.output is not supported")
                    continue
                if not target:
                    errors.append(f"{prefix}.target is required")
                    continue
                settings = outputs.get(output) if isinstance(outputs, dict) else None
                target_settings = settings.get(target) if isinstance(settings, dict) else None
                if not isinstance(target_settings, dict):
                    errors.append(f"{prefix} references missing {output}.{target}")
                else:
                    configured_secret = target_settings.get("secret")
                    if configured_secret is None:
                        configured_secret = target_settings.get("webhook")
                    route_enabled = destination.get("enabled", True) is True
                    target_enabled = (
                        settings.get("enabled", True) is True
                        and target_settings.get("enabled", True) is True
                    )
                    if route_enabled and target_enabled and output in {"discord", "teams", "slack", "webhook"} and configured_secret in (None, "", {}):
                        errors.append(f"outputs.{output}.{target} credentials are required")
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
