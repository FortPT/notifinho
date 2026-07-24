"""Database-authoritative runtime settings with per-resource validation."""

from __future__ import annotations

import ipaddress
import json
import re
import time

from copy import deepcopy
from dataclasses import dataclass
from typing import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from storage.audit_events import AuditEventStore
from storage.database import Database
from storage.ownership import Actor


_NAMESPACE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_KEY = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,95}$")
_MAC = re.compile(r"^[0-9A-F]{12}$")

DEFAULT_REGIONAL_SETTINGS = {
    "timezone": "Europe/Lisbon",
    "language": "en-GB",
    "time_format": "24",
}

DEFAULT_BACKUP_SETTINGS = {
    "schedule": "disabled",
    "time": "02:00",
    "weekday": 0,
    "day": 1,
    "target_id": "",
    "managed_mounts": False,
    "external_enabled": False,
    "external_type": "nfs",
    "external_path": "",
}

DEFAULT_INTEGRATION_SETTINGS = {
    "xo": {
        "success": False,
        "skipped": True,
        "failure": True,
        "show_ids": False,
    },
    "zabbix": {"show_ids": False},
    "dell_idrac": {"suppress_ipmi_session_audit_from": []},
    "unifi_protect": {"device_aliases": {}},
    "home_assistant": {
        "aliases": {"endpoints": {}, "components": {}},
    },
    "redfish": {"deduplication_window_seconds": 300},
}


class SettingsRecordError(RuntimeError):
    """One settings row is unavailable without breaking other resources."""

    def __init__(self, namespace: str, key: str, message: str):
        super().__init__(message)
        self.namespace = namespace
        self.key = key


@dataclass(frozen=True)
class SettingsRecord:
    namespace: str
    key: str
    value: dict
    updated_at: int


class SettingsStore:
    def __init__(
        self,
        database: Database,
        *,
        audit: AuditEventStore | None = None,
        clock: Callable[[], float] = time.time,
    ):
        self.database = database
        self.audit = audit
        self.clock = clock

    def get(self, namespace: str, key: str, default=None) -> dict:
        namespace, key = self._identity(namespace, key)
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT value_json, updated_at FROM settings_records
                WHERE namespace = ? AND setting_key = ?
                """,
                (namespace, key),
            ).fetchone()
        if row is None:
            return deepcopy({} if default is None else default)
        try:
            decoded = json.loads(str(row["value_json"]))
        except (TypeError, ValueError) as error:
            raise SettingsRecordError(
                namespace,
                key,
                "stored settings contain invalid JSON",
            ) from error
        if not isinstance(decoded, dict):
            raise SettingsRecordError(
                namespace,
                key,
                "stored settings must be an object",
            )
        try:
            return self.validate(namespace, key, decoded)
        except ValueError as error:
            raise SettingsRecordError(namespace, key, str(error)) from error

    def get_safe(self, namespace: str, key: str, default: dict) -> tuple[dict, dict | None]:
        """Load one row with a validated default instead of cascading failure."""

        try:
            return self.get(namespace, key, default), None
        except SettingsRecordError as error:
            return deepcopy(default), {
                "resource": key,
                "namespace": namespace,
                "code": "settings_record_invalid",
                "message": str(error),
            }

    def set(self, actor: Actor, namespace: str, key: str, value: dict) -> SettingsRecord:
        if not actor.is_admin:
            raise PermissionError("administrator access is required")
        namespace, key = self._identity(namespace, key)
        normalized = self.validate(namespace, key, value)
        encoded = json.dumps(
            normalized,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        if len(encoded.encode("utf-8")) > 64 * 1024:
            raise ValueError("settings must not exceed 65536 bytes")
        now = int(self.clock())
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO settings_records(
                    namespace, setting_key, value_json, updated_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(namespace, setting_key) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at = excluded.updated_at
                """,
                (namespace, key, encoded, now),
            )
        self._audit(
            actor,
            "settings.update",
            f"{namespace}:{key}",
            {"namespace": namespace, "key": key},
        )
        return SettingsRecord(namespace, key, normalized, now)

    def import_if_missing(self, namespace: str, key: str, value: dict) -> bool:
        namespace, key = self._identity(namespace, key)
        normalized = self.validate(namespace, key, value)
        encoded = json.dumps(
            normalized,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        now = int(self.clock())
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO settings_records(
                    namespace, setting_key, value_json, updated_at
                ) VALUES (?, ?, ?, ?)
                """,
                (namespace, key, encoded, now),
            )
        return bool(cursor.rowcount)

    def list_namespace(self, namespace: str) -> tuple[dict[str, dict], list[dict]]:
        namespace, _unused = self._identity(namespace, "placeholder")
        values: dict[str, dict] = {}
        errors: list[dict] = []
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT setting_key, value_json FROM settings_records
                WHERE namespace = ? ORDER BY setting_key
                """,
                (namespace,),
            ).fetchall()
        for row in rows:
            key = str(row["setting_key"])
            try:
                value = json.loads(str(row["value_json"]))
                if not isinstance(value, dict):
                    raise ValueError("stored settings must be an object")
                values[key] = self.validate(namespace, key, value)
            except (TypeError, ValueError) as error:
                errors.append(
                    {
                        "resource": key,
                        "code": "settings_record_invalid",
                        "message": str(error),
                    }
                )
        return values, errors

    @classmethod
    def validate(cls, namespace: str, key: str, value: dict) -> dict:
        if not isinstance(value, dict):
            raise ValueError("settings must be an object")
        if namespace == "platform" and key == "regional":
            return cls._regional(value)
        if namespace == "platform" and key == "backups":
            return cls._backups(value)
        if namespace == "integration":
            return cls._integration(key, value)
        raise ValueError("settings resource is not supported")

    @staticmethod
    def _regional(value: dict) -> dict:
        allowed = {"timezone", "language", "time_format"}
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"unsupported regional setting: {sorted(unknown)[0]}")
        timezone_name = str(value.get("timezone") or "").strip()
        try:
            if not timezone_name:
                raise ZoneInfoNotFoundError
            ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("timezone must be a valid IANA timezone") from None
        language = str(value.get("language") or "").strip()
        if language not in {"en-GB", "pt-PT"}:
            raise ValueError("language must be en-GB or pt-PT")
        time_format = str(value.get("time_format") or "").strip()
        if time_format not in {"12", "24"}:
            raise ValueError("time format must be 12 or 24")
        return {
            "timezone": timezone_name,
            "language": language,
            "time_format": time_format,
        }

    @classmethod
    def _backups(cls, value: dict) -> dict:
        allowed = set(DEFAULT_BACKUP_SETTINGS)
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"unsupported backup setting: {sorted(unknown)[0]}")
        schedule = str(value.get("schedule") or "disabled").strip().casefold()
        if schedule not in {"disabled", "daily", "weekly", "monthly"}:
            raise ValueError("backup schedule is invalid")
        clock_time = str(value.get("time") or "02:00").strip()
        if not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", clock_time):
            raise ValueError("backup time must use HH:MM")
        weekday = int(value.get("weekday", 0))
        day = int(value.get("day", 1))
        if not 0 <= weekday <= 6:
            raise ValueError("backup weekday must be between 0 and 6")
        if not 1 <= day <= 28:
            raise ValueError("backup day must be between 1 and 28")
        target_id = str(value.get("target_id") or "").strip()
        if target_id and not re.fullmatch(r"[0-9a-f]{32}", target_id):
            raise ValueError("backup target identifier is invalid")
        managed_mounts = cls._bool(value.get("managed_mounts", False), "managed_mounts")
        external_enabled = cls._bool(
            value.get("external_enabled", False), "external_enabled"
        )
        external_type = str(value.get("external_type") or "nfs").strip().casefold()
        if external_type not in {"nfs", "smb"}:
            raise ValueError("external backup type must be nfs or smb")
        external_path = str(value.get("external_path") or "").strip()
        if external_enabled and (
            not external_path.startswith("/") or external_path == "/"
        ):
            raise ValueError(
                "external backup path must be an absolute mounted directory"
            )
        return {
            "schedule": schedule,
            "time": clock_time,
            "weekday": weekday,
            "day": day,
            "target_id": target_id,
            "managed_mounts": managed_mounts,
            "external_enabled": external_enabled,
            "external_type": external_type,
            "external_path": external_path,
        }

    @classmethod
    def _integration(cls, key: str, value: dict) -> dict:
        if key == "xo":
            allowed = {"success", "skipped", "failure", "show_ids"}
            cls._unknown(value, allowed, key)
            return {
                name: cls._bool(value.get(name, DEFAULT_INTEGRATION_SETTINGS[key][name]), name)
                for name in ("success", "skipped", "failure", "show_ids")
            }
        if key == "zabbix":
            cls._unknown(value, {"show_ids"}, key)
            return {"show_ids": cls._bool(value.get("show_ids", False), "show_ids")}
        if key == "dell_idrac":
            cls._unknown(value, {"suppress_ipmi_session_audit_from"}, key)
            addresses = value.get("suppress_ipmi_session_audit_from", [])
            if not isinstance(addresses, list):
                raise ValueError("suppressed IPMI session clients must be a list")
            result = []
            for address in addresses:
                normalized = str(ipaddress.ip_address(str(address).strip()))
                if normalized not in result:
                    result.append(normalized)
            if len(result) > 128:
                raise ValueError("suppressed IPMI session clients must not exceed 128")
            return {"suppress_ipmi_session_audit_from": result}
        if key == "unifi_protect":
            cls._unknown(value, {"device_aliases"}, key)
            aliases = value.get("device_aliases", {})
            if not isinstance(aliases, dict):
                raise ValueError("UniFi Protect device aliases must be an object")
            result = {}
            for identifier, alias in aliases.items():
                compact = re.sub(r"[^0-9A-Fa-f]", "", str(identifier)).upper()
                if not _MAC.fullmatch(compact):
                    raise ValueError(f"invalid UniFi Protect identifier: {identifier}")
                display = str(alias or "").strip()
                if not display or len(display) > 160:
                    raise ValueError("UniFi Protect aliases must contain 1 to 160 characters")
                result[compact] = display
            return {"device_aliases": result}
        if key == "home_assistant":
            cls._unknown(value, {"aliases"}, key)
            aliases = value.get("aliases", {})
            if not isinstance(aliases, dict):
                raise ValueError("Home Assistant aliases must be an object")
            cls._unknown(aliases, {"endpoints", "components"}, "home_assistant.aliases")
            endpoints = cls._alias_map(aliases.get("endpoints", {}), endpoint=True)
            components = cls._alias_map(aliases.get("components", {}), endpoint=False)
            return {"aliases": {"endpoints": endpoints, "components": components}}
        if key == "redfish":
            cls._unknown(value, {"deduplication_window_seconds"}, key)
            seconds = int(value.get("deduplication_window_seconds", 300))
            if not 0 <= seconds <= 86400:
                raise ValueError(
                    "Redfish deduplication window must be between 0 and 86400 seconds"
                )
            return {"deduplication_window_seconds": seconds}
        raise ValueError("integration settings are not supported")

    @classmethod
    def _alias_map(cls, value, *, endpoint: bool) -> dict:
        if not isinstance(value, dict):
            raise ValueError("Home Assistant alias entries must be an object")
        result = {}
        for name, settings in value.items():
            identity = str(name or "").strip()
            if not identity or len(identity) > 240:
                raise ValueError("Home Assistant alias identifiers are invalid")
            if isinstance(settings, str):
                settings = {"device": settings}
            if not isinstance(settings, dict):
                raise ValueError("Home Assistant alias values must be objects")
            allowed = {"device"} if endpoint else {"device", "endpoint"}
            cls._unknown(settings, allowed, f"home_assistant.{identity}")
            item = {}
            for field in allowed:
                text = str(settings.get(field) or "").strip()
                if text:
                    if len(text) > 240:
                        raise ValueError("Home Assistant alias values are too long")
                    item[field] = text
            if not item.get("device"):
                raise ValueError("Home Assistant aliases require a device name")
            result[identity] = item
        return result

    @staticmethod
    def _bool(value, name: str) -> bool:
        if not isinstance(value, bool):
            raise ValueError(f"{name} must be a boolean")
        return value

    @staticmethod
    def _unknown(value: dict, allowed: set[str], label: str) -> None:
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"unsupported {label} setting: {sorted(unknown)[0]}")

    @staticmethod
    def _identity(namespace: str, key: str) -> tuple[str, str]:
        normalized_namespace = str(namespace or "").strip().casefold()
        normalized_key = str(key or "").strip().casefold()
        if not _NAMESPACE.fullmatch(normalized_namespace):
            raise ValueError("settings namespace is invalid")
        if not _KEY.fullmatch(normalized_key):
            raise ValueError("settings key is invalid")
        return normalized_namespace, normalized_key

    def _audit(self, actor, action, resource_id, details=None):
        if self.audit is not None:
            self.audit.write(
                actor,
                action,
                "settings",
                resource_id,
                "success",
                details,
            )


def runtime_overlay_status(settings: SettingsStore) -> tuple[dict, list[dict]]:
    """Build the compatibility overlay while isolating damaged settings rows."""

    errors: list[dict] = []
    regional, error = settings.get_safe(
        "platform",
        "regional",
        DEFAULT_REGIONAL_SETTINGS,
    )
    if error:
        errors.append(error)
    backups, error = settings.get_safe(
        "platform",
        "backups",
        DEFAULT_BACKUP_SETTINGS,
    )
    if error:
        errors.append(error)
    integrations = {}
    for key, default in DEFAULT_INTEGRATION_SETTINGS.items():
        value, error = settings.get_safe("integration", key, default)
        integrations[key] = value
        if error:
            errors.append(error)
    overlay = {
        "presentation": {
            "timezone": regional["timezone"],
            "time_format": regional["time_format"],
        },
        "webui": {"language": regional["language"]},
        "platform": {"backups": backups},
        "notifications": {
            "xo": integrations["xo"],
            "zabbix": integrations["zabbix"],
            "dell_idrac": integrations["dell_idrac"],
            "unifi_protect": integrations["unifi_protect"],
        },
        "home_assistant": integrations["home_assistant"],
        "redfish": integrations["redfish"],
    }
    return overlay, errors


def runtime_overlay(settings: SettingsStore) -> dict:
    """Return the in-memory compatibility view consumed by existing parsers."""

    return runtime_overlay_status(settings)[0]
