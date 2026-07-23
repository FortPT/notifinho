"""Keep config.yaml authoritative while SQLite provides a runtime mirror."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from api.schema import validate_config
from outputs.settings import OUTPUT_TYPES, normalize_output_settings
from storage.audit_events import AuditEventStore
from storage.destinations import DestinationStore
from storage.ownership import Actor
from storage.routes import RouteStore, route_priority_name, route_priority_value
from storage.secrets import SecretStore
from storage.validation import normalized_name


CONFIGURATION_MODEL = "unified_yaml_v1"
_SYNC_LOCK = threading.RLock()
_TARGET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
_ROUTE_ID = re.compile(r"^[0-9a-f]{12,32}$")
_INTERNAL_OUTPUT_FIELDS = {
    "enabled",
    "name",
    "settings",
    "shared",
    "secret",
    "webhook",
}


@dataclass(frozen=True)
class ConfigurationSyncStatus:
    ready: bool
    changed: bool
    fingerprint: str
    owner_user_id: str | None
    errors: tuple[str, ...] = ()


class UnifiedConfigurationService:
    """Synchronize, inspect, and mutate YAML-backed platform resources.

    YAML is the durable source of truth. SQLite rows and secret files are a
    private mirror used by the existing delivery, history, preview, and retry
    services. This keeps CLI-only operation possible without exposing secrets
    through the browser API.
    """

    def __init__(self, config_service, database, *, audit=None):
        self.config_service = config_service
        self.database = database
        self.audit = audit or AuditEventStore(database)
        self.secrets = SecretStore(database)
        self._fingerprint = ""

    def synchronize(self, *, force: bool = False) -> ConfigurationSyncStatus:
        with _SYNC_LOCK:
            _reloaded, refresh_errors = self.config_service.refresh()
            try:
                source = self.config_service.source_text()
                data = self._decode(source)
            except (OSError, ValueError) as error:
                return ConfigurationSyncStatus(
                    False,
                    False,
                    "",
                    None,
                    (str(error),),
                )
            errors = tuple(validate_config(data))
            if refresh_errors:
                errors = tuple(dict.fromkeys([*refresh_errors, *errors]))
            if errors:
                return ConfigurationSyncStatus(False, False, "", None, errors)
            fingerprint = hashlib.sha256(source.encode("utf-8")).hexdigest()
            owner_id = self._configuration_owner()
            if owner_id is None:
                return ConfigurationSyncStatus(
                    False,
                    False,
                    fingerprint,
                    None,
                    ("create the first administrator before WebUI synchronization",),
                )
            if not force and fingerprint == self._fingerprint:
                return ConfigurationSyncStatus(True, False, fingerprint, owner_id)

            actor = Actor(owner_id, "admin")
            changed = self._synchronize_data(actor, data, remove_stale=False)
            platform = data.get("platform") if isinstance(data.get("platform"), dict) else {}
            if platform.get("configuration_model") != CONFIGURATION_MODEL:
                candidate = deepcopy(data)
                adopted = self._adopt_unmanaged(candidate, actor)
                candidate_platform = candidate.setdefault("platform", {})
                candidate_platform["configuration_model"] = CONFIGURATION_MODEL
                candidate_platform.pop("routing_authority", None)
                self.config_service.replace(candidate)
                source = self.config_service.source_text()
                data = self._decode(source)
                fingerprint = hashlib.sha256(source.encode("utf-8")).hexdigest()
                changed = self._synchronize_data(actor, data, remove_stale=True) or changed
                changed = True
                self._audit(
                    actor,
                    "configuration.unify",
                    "success",
                    {"database_resources_adopted": adopted},
                )
            else:
                changed = self._synchronize_data(actor, data, remove_stale=True) or changed
            self._fingerprint = fingerprint
            return ConfigurationSyncStatus(True, changed, fingerprint, owner_id)

    def list_destinations(self, actor: Actor) -> list:
        self.synchronize()
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM destinations
                WHERE configuration_key IS NOT NULL
                ORDER BY name_normalized
                """
            ).fetchall()
        # Every YAML destination is intentionally visible; only administrators
        # can mutate the shared configuration file.
        return [DestinationStore._destination(row) for row in rows]

    def list_routes(self, actor: Actor) -> list:
        self.synchronize()
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM routes
                WHERE configuration_key IS NOT NULL
                ORDER BY priority, name_normalized
                """
            ).fetchall()
        return [RouteStore._route(row) for row in rows]

    def create_destination(self, actor: Actor, data: dict):
        self._require_admin(actor)
        self._ready()
        output_type = str(data.get("output_type") or "").strip().casefold()
        if output_type not in OUTPUT_TYPES:
            raise ValueError("unsupported destination output type")
        display, _normalized = normalized_name(data.get("name"), "destination name")
        target = self._new_target(display, output_type)
        settings = normalize_output_settings(output_type, data.get("settings", {}))
        enabled = self._boolean(data.get("enabled", True), "enabled")
        secret = data.get("secret")
        candidate = self.config_service.snapshot()
        group = candidate.setdefault("outputs", {}).setdefault(output_type, {})
        if not isinstance(group, dict):
            raise ValueError("output group must be an object")
        group.setdefault("enabled", True)
        group[target] = self._destination_entry(
            output_type,
            display,
            settings,
            enabled,
            secret,
            self._boolean(data.get("shared", True), "shared"),
        )
        self.config_service.replace(candidate)
        self.synchronize(force=True)
        item = self._destination_by_key(f"destination:{output_type}:{target}")
        self._audit(actor, "destination.create", "success", {"target": target})
        return item

    def update_destination(self, actor: Actor, destination_id: str, data: dict):
        self._require_admin(actor)
        self._ready()
        output_type, target = self._destination_location(destination_id)
        candidate = self.config_service.snapshot()
        entry = self._destination_yaml(candidate, output_type, target)
        current = self._parse_destination(output_type, target, entry)
        display, _normalized = normalized_name(
            data.get("name", current["name"]),
            "destination name",
        )
        settings = (
            normalize_output_settings(output_type, data["settings"])
            if "settings" in data
            else current["settings"]
        )
        enabled = (
            self._boolean(data["enabled"], "enabled")
            if "enabled" in data
            else current["enabled"]
        )
        secret = data.get("secret", current["secret_value"])
        shared = (
            self._boolean(data["shared"], "shared")
            if "shared" in data
            else current["shared"]
        )
        candidate["outputs"][output_type][target] = self._destination_entry(
            output_type,
            display,
            settings,
            enabled,
            secret,
            shared,
        )
        self.config_service.replace(candidate)
        self.synchronize(force=True)
        self._audit(actor, "destination.update", "success", {"target": target})
        return self._destination_by_key(f"destination:{output_type}:{target}")

    def delete_destination(self, actor: Actor, destination_id: str) -> None:
        self._require_admin(actor)
        self._ready()
        output_type, target = self._destination_location(destination_id)
        candidate = self.config_service.snapshot()
        for source, position, entry in self._route_entries(candidate):
            if (
                str(entry.get("output") or "").casefold() == output_type
                and str(entry.get("target", "default")) == target
            ):
                raise ValueError("destination is referenced by a route")
        group = candidate.get("outputs", {}).get(output_type)
        if not isinstance(group, dict) or target not in group:
            raise KeyError("destination not found")
        del group[target]
        if not [key for key in group if key != "enabled"]:
            candidate["outputs"].pop(output_type, None)
        self.config_service.replace(candidate)
        self.synchronize(force=True)
        self._audit(actor, "destination.delete", "success", {"target": target})

    def create_route(self, actor: Actor, data: dict):
        self._require_admin(actor)
        self._ready()
        source = RouteStore._source(data.get("source"))
        destination_type, target = self._destination_location(data.get("destination_id"))
        display, _normalized = normalized_name(data.get("name"), "route name")
        filters = self._decoded_filters(data.get("filters", {}))
        priority = self._priority(data.get("priority", 100))
        enabled = self._boolean(data.get("enabled", True), "enabled")
        route_key = uuid.uuid4().hex[:16]
        candidate = self.config_service.snapshot()
        routes = candidate.setdefault("routing", {})
        section = routes.setdefault(source, {"outputs": []})
        entries = section.setdefault("outputs", [])
        if not isinstance(entries, list):
            raise ValueError("route outputs must be a list")
        entries.append(
            self._route_entry(
                route_key,
                display,
                destination_type,
                target,
                filters,
                priority,
                enabled,
            )
        )
        self.config_service.replace(candidate)
        self.synchronize(force=True)
        self._audit(actor, "route.create", "success", {"source": source})
        return self._route_by_key(f"route:{route_key}")

    def update_route(self, actor: Actor, route_id: str, data: dict):
        self._require_admin(actor)
        self._ready()
        key = self._route_configuration_key(route_id)
        candidate = self.config_service.snapshot()
        source, position, entry = self._find_route(candidate, key)
        next_source = RouteStore._source(data.get("source", source))
        destination_type, target = self._destination_location(
            data.get("destination_id") or self._destination_id_for_entry(entry)
        )
        display, _normalized = normalized_name(
            data.get("name", entry.get("name") or self._route_name(source, entry)),
            "route name",
        )
        filters = self._decoded_filters(data.get("filters", entry.get("match", {})))
        priority = self._priority(data.get("priority", entry.get("priority", 100)))
        enabled = self._boolean(data.get("enabled", entry.get("enabled", True)), "enabled")
        route_key = key.split(":", 1)[1]
        replacement = self._route_entry(
            route_key,
            display,
            destination_type,
            target,
            filters,
            priority,
            enabled,
        )
        self._remove_route_position(candidate, source, position)
        candidate.setdefault("routing", {}).setdefault(next_source, {"outputs": []}).setdefault("outputs", []).append(replacement)
        self.config_service.replace(candidate)
        self.synchronize(force=True)
        self._audit(actor, "route.update", "success", {"source": next_source})
        return self._route_by_key(key)

    def delete_route(self, actor: Actor, route_id: str) -> None:
        self._require_admin(actor)
        self._ready()
        key = self._route_configuration_key(route_id)
        candidate = self.config_service.snapshot()
        source, position, _entry = self._find_route(candidate, key)
        self._remove_route_position(candidate, source, position)
        self.config_service.replace(candidate)
        self.synchronize(force=True)
        self._audit(actor, "route.delete", "success", {"source": source})

    def legacy_applications(self) -> list[dict]:
        self.synchronize()
        tokens = self.config_service.configuration.get("api", "tokens", default={})
        if not isinstance(tokens, dict):
            return []
        applications = []
        with self.database.connect() as connection:
            usage = {
                str(row["application_name"]): (
                    int(row["last_used_at"]),
                    int(row["request_count"]),
                )
                for row in connection.execute("SELECT * FROM application_usage")
            }
        for name, settings in tokens.items():
            if not isinstance(settings, dict):
                continue
            configured_by = "not configured"
            credential_available = False
            if settings.get("token_env"):
                configured_by = "environment"
                credential_available = bool(os.environ.get(str(settings["token_env"])))
            elif settings.get("token_file"):
                configured_by = "secret file"
                path = Path(str(settings["token_file"]))
                credential_available = path.is_file() and os.access(path, os.R_OK)
            elif settings.get("token_sha256"):
                configured_by = "SHA-256"
                credential_available = True
            sources = settings.get("sources") or []
            if isinstance(sources, str):
                sources = [sources]
            last_used_at, request_count = usage.get(str(name), (None, 0))
            applications.append(
                {
                    "id": f"yaml-{hashlib.sha256(str(name).encode()).hexdigest()[:24]}",
                    "name": str(name),
                    "role": str(settings.get("role") or "application"),
                    "source_scopes": [str(value) for value in sources],
                    "rate_limit_per_minute": int(settings.get("rate_limit_per_minute", 60)),
                    "version": 1,
                    "created_at": None,
                    "updated_at": None,
                    "expires_at": None,
                    "last_used_at": last_used_at,
                    "request_count": request_count,
                    "revoked_at": None,
                    "enabled": settings.get("enabled", True) is True,
                    "management": "yaml",
                    "credential_source": configured_by,
                    "credential_available": credential_available,
                }
            )
        return applications

    def record_application_usage(self, name: str) -> None:
        application_name = str(name or "")[:128]
        if not application_name:
            return
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO application_usage(application_name, last_used_at, request_count)
                VALUES (?, ?, 1)
                ON CONFLICT(application_name) DO UPDATE SET
                    last_used_at = excluded.last_used_at,
                    request_count = application_usage.request_count + 1
                """,
                (application_name, int(time.time())),
            )

    def update_application(self, actor: Actor, application_id: str, *, enabled: bool):
        self._require_admin(actor)
        self._ready()
        name = self._application_name(application_id)
        candidate = self.config_service.snapshot()
        tokens = candidate.get("api", {}).get("tokens", {})
        if not isinstance(tokens, dict) or not isinstance(tokens.get(name), dict):
            raise KeyError("application not found")
        tokens[name]["enabled"] = self._boolean(enabled, "enabled")
        self.config_service.replace(candidate)
        self.synchronize(force=True)
        self._audit(
            actor,
            "application.enable" if enabled else "application.disable",
            "success",
            {"name": name},
        )
        return next(
            item for item in self.legacy_applications()
            if item["id"] == application_id
        )

    def delete_application(self, actor: Actor, application_id: str) -> None:
        self._require_admin(actor)
        self._ready()
        name = self._application_name(application_id)
        candidate = self.config_service.snapshot()
        api = candidate.get("api")
        tokens = api.get("tokens") if isinstance(api, dict) else None
        if not isinstance(tokens, dict) or name not in tokens:
            raise KeyError("application not found")
        del tokens[name]
        self.config_service.replace(candidate)
        self.synchronize(force=True)
        with self.database.transaction() as connection:
            connection.execute(
                "DELETE FROM application_usage WHERE application_name = ?",
                (name,),
            )
        self._audit(actor, "application.delete", "success", {"name": name})

    def preferences(self) -> dict:
        self.synchronize()
        presentation = self.config_service.configuration.get("presentation", default={}) or {}
        webui = self.config_service.configuration.get("webui", default={}) or {}
        return {
            "timezone": str(presentation.get("timezone") or "Europe/Lisbon"),
            "language": str(webui.get("language") or "en-GB"),
            "time_format": str(presentation.get("time_format") or "24"),
        }

    def update_preferences(self, actor: Actor, values: dict) -> dict:
        self._require_admin(actor)
        timezone_name = str(values.get("timezone") or "").strip()
        language = str(values.get("language") or "").strip()
        time_format = str(values.get("time_format") or "").strip()
        if language not in {"en-GB", "pt-PT"}:
            raise ValueError("unsupported language")
        if time_format not in {"12", "24"}:
            raise ValueError("time format must be 12 or 24")
        candidate = self.config_service.snapshot()
        presentation = candidate.setdefault("presentation", {})
        presentation["timezone"] = timezone_name
        presentation["time_format"] = time_format
        webui = candidate.setdefault("webui", {})
        webui["language"] = language
        webui.pop("time_format", None)
        errors = validate_config(candidate)
        if errors:
            raise ValueError("; ".join(errors))
        self.config_service.replace(candidate)
        self.synchronize(force=True)
        self._audit(actor, "preferences.update", "success", self.preferences())
        return self.preferences()

    def update_input(self, actor: Actor, name: str, enabled: bool) -> dict:
        self._require_admin(actor)
        self._ready()
        input_name = str(name or "").strip().casefold()
        if input_name not in {"smtp", "http", "redfish", "home_assistant", "unifi"}:
            raise ValueError("input is not managed by the WebUI")
        candidate = self.config_service.snapshot()
        section = candidate.get(input_name)
        if section is None:
            section = {}
            candidate[input_name] = section
        if not isinstance(section, dict):
            raise ValueError("input configuration must be an object")
        section["enabled"] = self._boolean(enabled, "enabled")
        self.config_service.replace(candidate)
        self.synchronize(force=True)
        self._audit(
            actor,
            "input.enable" if enabled else "input.disable",
            "success",
            {"input": input_name, "restart_required": True},
        )
        return {
            "name": input_name,
            "enabled": enabled,
            "restart_required": True,
        }

    def backup_settings(self) -> dict:
        self.synchronize()
        platform = self.config_service.configuration.get("platform", default={}) or {}
        values = platform.get("backups") if isinstance(platform, dict) else {}
        values = values if isinstance(values, dict) else {}
        return {
            "schedule": str(values.get("schedule") or "disabled"),
            "time": str(values.get("time") or "02:00"),
            "weekday": int(values.get("weekday", 0)),
            "day": int(values.get("day", 1)),
            "target_id": str(values.get("target_id") or ""),
            "managed_mounts": values.get("managed_mounts", False) is True,
            "external_enabled": values.get("external_enabled", False) is True,
            "external_type": str(values.get("external_type") or "nfs"),
            "external_path": str(values.get("external_path") or ""),
        }

    def update_backup_settings(self, actor: Actor, values: dict) -> dict:
        self._require_admin(actor)
        self._ready()
        schedule = str(values.get("schedule") or "").strip().casefold()
        clock_time = str(values.get("time") or "").strip()
        external_type = str(values.get("external_type") or "").strip().casefold()
        external_path = str(values.get("external_path") or "").strip()
        external_enabled = self._boolean(values.get("external_enabled"), "external_enabled")
        target_id = str(values.get("target_id") or "").strip()
        managed_mounts = self._boolean(
            values.get("managed_mounts", False), "managed_mounts"
        )
        if target_id and not re.fullmatch(r"[0-9a-f]{32}", target_id):
            raise ValueError("backup target identifier is invalid")
        if schedule not in {"disabled", "daily", "weekly", "monthly"}:
            raise ValueError("backup schedule is invalid")
        if not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", clock_time):
            raise ValueError("backup time must use HH:MM")
        if external_type not in {"nfs", "smb"}:
            raise ValueError("external backup type must be NFS or SMB")
        if external_enabled and (
            not external_path.startswith("/") or external_path == "/"
        ):
            raise ValueError("external backup path must be an absolute mounted directory")
        weekday = int(values.get("weekday", 0))
        day = int(values.get("day", 1))
        if not 0 <= weekday <= 6 or not 1 <= day <= 28:
            raise ValueError("backup weekday or day is invalid")
        candidate = self.config_service.snapshot()
        platform = candidate.setdefault("platform", {})
        platform["backups"] = {
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
        errors = validate_config(candidate)
        if errors:
            raise ValueError("; ".join(errors))
        self.config_service.replace(candidate)
        self.synchronize(force=True)
        self._audit(actor, "backup.schedule.update", "success", self.backup_settings())
        return self.backup_settings()

    def adopt_unmanaged_resources(self, actor: Actor) -> int:
        """Move newly imported database resources into authoritative YAML."""

        self._require_admin(actor)
        with _SYNC_LOCK:
            candidate = self.config_service.snapshot()
            adopted = self._adopt_unmanaged(candidate, actor)
            if adopted:
                candidate.setdefault("platform", {})["configuration_model"] = CONFIGURATION_MODEL
                candidate["platform"].pop("routing_authority", None)
                self.config_service.replace(candidate)
                self.synchronize(force=True)
            return adopted

    def _ready(self) -> ConfigurationSyncStatus:
        status = self.synchronize()
        if not status.ready:
            raise ValueError("; ".join(status.errors) or "configuration is unavailable")
        return status

    def _synchronize_data(self, actor: Actor, data: dict, *, remove_stale: bool) -> bool:
        changed = False
        destination_ids = {}
        destination_keys = set()
        for spec in self._destination_specs(data):
            destination = self._upsert_destination(actor, spec)
            destination_ids[(spec["output_type"], spec["target"])] = destination.id
            destination_keys.add(spec["key"])
            changed = changed or spec.get("changed", False)
        route_keys = set()
        for spec in self._route_specs(data, destination_ids):
            self._upsert_route(actor, spec)
            route_keys.add(spec["key"])
        if remove_stale:
            changed = self._remove_stale(actor, destination_keys, route_keys) or changed
        return changed

    def _upsert_destination(self, actor: Actor, spec: dict):
        key = spec["key"]
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM destinations WHERE configuration_key = ?",
                (key,),
            ).fetchone()
            if row is None:
                alternatives = [
                    spec["target"].casefold(),
                    spec["name"].casefold(),
                    f"imported {spec['output_type']} {spec['target']}".casefold(),
                ]
                marks = ",".join("?" for _ in alternatives)
                row = connection.execute(
                    f"""
                    SELECT * FROM destinations
                    WHERE configuration_key IS NULL
                      AND owner_user_id = ? AND output_type = ?
                      AND name_normalized IN ({marks})
                    ORDER BY created_at LIMIT 1
                    """,
                    (actor.user_id, spec["output_type"], *alternatives),
                ).fetchone()
        encoded_settings = DestinationStore._settings(spec["output_type"], spec["settings"])
        display, normalized = normalized_name(spec["name"], "destination name")
        now = int(time.time())
        if row is None:
            destination_id = uuid.uuid4().hex
            with self.database.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO destinations(
                        id, owner_user_id, name, name_normalized, output_type,
                        settings_json, shared, enabled, created_at, updated_at,
                        configuration_key
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        destination_id,
                        actor.user_id,
                        display,
                        normalized,
                        spec["output_type"],
                        encoded_settings,
                        1 if spec["shared"] else 0,
                        1 if spec["enabled"] else 0,
                        now,
                        now,
                        key,
                    ),
                )
        else:
            destination_id = str(row["id"])
            with self.database.transaction() as connection:
                connection.execute(
                    """
                    UPDATE destinations
                    SET owner_user_id = ?, name = ?, name_normalized = ?,
                        output_type = ?, settings_json = ?, shared = ?,
                        enabled = ?, updated_at = ?, configuration_key = ?
                    WHERE id = ?
                    """,
                    (
                        actor.user_id,
                        display,
                        normalized,
                        spec["output_type"],
                        encoded_settings,
                        1 if spec["shared"] else 0,
                        1 if spec["enabled"] else 0,
                        now,
                        key,
                        destination_id,
                    ),
                )
        self._sync_secret(actor, destination_id, display, spec["output_type"], spec["secret_value"])
        return self._destination_by_key(key)

    def _sync_secret(self, actor, destination_id, name, output_type, value):
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT secret_id FROM destinations WHERE id = ?",
                (destination_id,),
            ).fetchone()
        secret_id = str(row["secret_id"]) if row and row["secret_id"] else None
        if value is None:
            if secret_id:
                with self.database.transaction() as connection:
                    connection.execute(
                        "UPDATE destinations SET secret_id = NULL WHERE id = ?",
                        (destination_id,),
                    )
                self.secrets.delete(actor, secret_id)
            return
        payload = self._secret_payload(value)
        if secret_id:
            current = self.secrets.resolve(actor, secret_id)
            if current != payload:
                self.secrets.rotate(actor, secret_id, payload)
            return
        secret = self.secrets.create(
            actor,
            actor.user_id,
            f"config {output_type} {name} {uuid.uuid4().hex[:8]}",
            f"{output_type}-credentials",
            payload,
        )
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE destinations SET secret_id = ? WHERE id = ?",
                (secret.id, destination_id),
            )

    def _upsert_route(self, actor: Actor, spec: dict):
        key = spec["key"]
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM routes WHERE configuration_key = ?",
                (key,),
            ).fetchone()
            if row is None:
                row = connection.execute(
                    """
                    SELECT * FROM routes
                    WHERE configuration_key IS NULL AND owner_user_id = ?
                      AND source = ? AND destination_id = ?
                    ORDER BY priority, created_at LIMIT 1
                    """,
                    (actor.user_id, spec["source"], spec["destination_id"]),
                ).fetchone()
        display, normalized = normalized_name(spec["name"], "route name")
        source = RouteStore._source(spec["source"])
        filters_json = RouteStore._filters(spec["filters"])
        now = int(time.time())
        if row is None:
            route_id = uuid.uuid4().hex
            with self.database.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO routes(
                        id, owner_user_id, destination_id, name, name_normalized,
                        source, filters_json, priority, enabled, created_at,
                        updated_at, configuration_key
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        route_id,
                        actor.user_id,
                        spec["destination_id"],
                        display,
                        normalized,
                        source,
                        filters_json,
                        spec["priority"],
                        1 if spec["enabled"] else 0,
                        now,
                        now,
                        key,
                    ),
                )
        else:
            route_id = str(row["id"])
            with self.database.transaction() as connection:
                connection.execute(
                    """
                    UPDATE routes
                    SET owner_user_id = ?, destination_id = ?, name = ?,
                        name_normalized = ?, source = ?, filters_json = ?,
                        priority = ?, enabled = ?, updated_at = ?,
                        configuration_key = ?
                    WHERE id = ?
                    """,
                    (
                        actor.user_id,
                        spec["destination_id"],
                        display,
                        normalized,
                        source,
                        filters_json,
                        spec["priority"],
                        1 if spec["enabled"] else 0,
                        now,
                        key,
                        route_id,
                    ),
                )
        return self._route_by_key(key)

    def _remove_stale(self, actor, destination_keys, route_keys):
        changed = False
        with self.database.transaction() as connection:
            rows = connection.execute(
                "SELECT id, configuration_key FROM routes WHERE configuration_key IS NOT NULL"
            ).fetchall()
            for row in rows:
                if str(row["configuration_key"]) not in route_keys:
                    connection.execute("DELETE FROM routes WHERE id = ?", (row["id"],))
                    changed = True
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT id, secret_id, configuration_key FROM destinations WHERE configuration_key IS NOT NULL"
            ).fetchall()
        for row in rows:
            if str(row["configuration_key"]) in destination_keys:
                continue
            secret_id = str(row["secret_id"]) if row["secret_id"] else None
            with self.database.transaction() as connection:
                connection.execute("DELETE FROM destinations WHERE id = ?", (row["id"],))
            if secret_id:
                self.secrets.delete(actor, secret_id)
            changed = True
        return changed

    def _adopt_unmanaged(self, candidate: dict, actor: Actor) -> int:
        adopted = 0
        outputs = candidate.setdefault("outputs", {})
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM destinations
                WHERE configuration_key IS NULL AND owner_user_id = ?
                ORDER BY created_at
                """,
                (actor.user_id,),
            ).fetchall()
        adopted_targets = {}
        for row in rows:
            output_type = str(row["output_type"])
            group = outputs.setdefault(output_type, {"enabled": True})
            target = self._new_target(str(row["name"]), output_type, data=candidate)
            settings = json.loads(str(row["settings_json"]))
            secret = None
            if row["secret_id"]:
                secret = self._decode_secret_value(
                    output_type,
                    self.secrets.resolve(actor, str(row["secret_id"])),
                )
            group[target] = self._destination_entry(
                output_type,
                str(row["name"]),
                settings,
                bool(row["enabled"]),
                secret,
            )
            adopted_targets[str(row["id"])] = (output_type, target)
            adopted += 1
        if adopted_targets:
            routing = candidate.setdefault("routing", {})
            with self.database.connect() as connection:
                routes = connection.execute(
                    """
                    SELECT * FROM routes
                    WHERE configuration_key IS NULL AND owner_user_id = ?
                    ORDER BY priority, created_at
                    """,
                    (actor.user_id,),
                ).fetchall()
            for row in routes:
                destination = adopted_targets.get(str(row["destination_id"]))
                if destination is None:
                    continue
                source = str(row["source"])
                routing.setdefault(source, {"outputs": []}).setdefault("outputs", []).append(
                    self._route_entry(
                        uuid.uuid4().hex[:16],
                        str(row["name"]),
                        destination[0],
                        destination[1],
                        json.loads(str(row["filters_json"])),
                        int(row["priority"]),
                        bool(row["enabled"]),
                    )
                )
                adopted += 1
        return adopted

    def _destination_specs(self, data):
        outputs = data.get("outputs") or {}
        for output_type, group in outputs.items():
            normalized_type = str(output_type).casefold()
            if normalized_type not in OUTPUT_TYPES or not isinstance(group, dict):
                continue
            group_enabled = group.get("enabled", True) is True
            for target, entry in group.items():
                if target == "enabled" or not isinstance(entry, dict):
                    continue
                parsed = self._parse_destination(normalized_type, str(target), entry)
                parsed["enabled"] = group_enabled and parsed["enabled"]
                parsed["key"] = f"destination:{normalized_type}:{target}"
                yield parsed

    def _route_specs(self, data, destination_ids):
        for source, position, entry in self._route_entries(data):
            output_type = str(entry.get("output") or "").casefold()
            target = str(entry.get("target", "default"))
            destination_id = destination_ids.get((output_type, target))
            if destination_id is None:
                continue
            route_key = str(entry.get("id") or f"legacy-{source}-{position}")
            yield {
                "key": f"route:{route_key}",
                "name": str(entry.get("name") or self._route_name(source, entry)),
                "source": str(source),
                "destination_id": destination_id,
                "filters": self._decoded_filters(entry.get("match", {})),
                "priority": self._priority(entry.get("priority", 100 + position)),
                "enabled": entry.get("enabled", True) is True,
            }

    def _parse_destination(self, output_type, target, entry):
        nested = entry.get("settings")
        if nested is None:
            nested = {
                key: value
                for key, value in entry.items()
                if key not in _INTERNAL_OUTPUT_FIELDS
            }
        settings = normalize_output_settings(output_type, nested or {})
        secret = entry.get("secret")
        if secret is None and "webhook" in entry:
            secret = entry.get("webhook")
        return {
            "output_type": output_type,
            "target": target,
            "name": str(entry.get("name") or target),
            "settings": settings,
            "enabled": entry.get("enabled", True) is True,
            "shared": entry.get("shared", True) is True,
            "secret_value": secret,
        }

    def _destination_entry(self, output_type, name, settings, enabled, secret, shared=True):
        entry = {"name": name, "enabled": bool(enabled), "shared": bool(shared)}
        if settings:
            entry["settings"] = deepcopy(settings)
        if secret is not None:
            if output_type in {"discord", "teams"}:
                if isinstance(secret, dict):
                    entry["webhook"] = str(secret.get("url") or secret.get("value") or "")
                else:
                    entry["webhook"] = str(secret)
            else:
                entry["secret"] = deepcopy(secret)
        return entry

    @staticmethod
    def _route_entry(route_key, name, output_type, target, filters, priority, enabled):
        entry = {
            "id": route_key,
            "name": name,
            "output": output_type,
            "target": target,
            "priority": route_priority_name(priority),
            "enabled": bool(enabled),
        }
        if filters:
            entry["match"] = {key: list(values) for key, values in filters.items()}
        return entry

    @staticmethod
    def _route_entries(data):
        routing = data.get("routing") or {}
        if not isinstance(routing, dict):
            return []
        result = []
        for source, section in routing.items():
            if not isinstance(section, dict):
                continue
            entries = section.get("outputs")
            if entries is None:
                entries = [section]
            if not isinstance(entries, list):
                continue
            for position, entry in enumerate(entries):
                if isinstance(entry, dict):
                    result.append((str(source), position, entry))
        return result

    @staticmethod
    def _route_name(source, entry):
        return f"{source} to {entry.get('output')} {entry.get('target', 'default')}"

    @staticmethod
    def _decoded_filters(value):
        encoded = RouteStore._filters(value or {})
        return json.loads(encoded)

    @staticmethod
    def _priority(value):
        return route_priority_value(value)

    @staticmethod
    def _boolean(value, name):
        if not isinstance(value, bool):
            raise ValueError(f"{name} must be a boolean")
        return value

    @staticmethod
    def _secret_payload(value):
        if isinstance(value, dict):
            return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if isinstance(value, bytes):
            return value
        text = str(value or "")
        if not text:
            raise ValueError("configured destination secret is empty")
        return text.encode("utf-8")

    @staticmethod
    def _decode_secret_value(output_type, payload):
        text = payload.decode("utf-8")
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            value = text
        if output_type in {"discord", "teams"} and isinstance(value, dict):
            return value.get("url") or value.get("value") or ""
        return value

    def _configuration_owner(self):
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT id FROM users
                WHERE role = 'admin' AND enabled = 1
                ORDER BY created_at, id LIMIT 1
                """
            ).fetchone()
        return str(row["id"]) if row is not None else None

    def _application_name(self, application_id: str) -> str:
        wanted = str(application_id or "")
        for item in self.legacy_applications():
            if item["id"] == wanted:
                return item["name"]
        raise KeyError("application not found")

    def _destination_location(self, destination_id):
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT configuration_key FROM destinations WHERE id = ?",
                (str(destination_id),),
            ).fetchone()
        if row is None or not row["configuration_key"]:
            raise KeyError("destination not found")
        _label, output_type, target = str(row["configuration_key"]).split(":", 2)
        return output_type, target

    def _destination_by_key(self, key):
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM destinations WHERE configuration_key = ?",
                (key,),
            ).fetchone()
        if row is None:
            raise KeyError("destination not found")
        return DestinationStore._destination(row)

    def _route_by_key(self, key):
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM routes WHERE configuration_key = ?",
                (key,),
            ).fetchone()
        if row is None:
            raise KeyError("route not found")
        return RouteStore._route(row)

    def _route_configuration_key(self, route_id):
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT configuration_key FROM routes WHERE id = ?",
                (str(route_id),),
            ).fetchone()
        if row is None or not row["configuration_key"]:
            raise KeyError("route not found")
        return str(row["configuration_key"])

    def _destination_yaml(self, data, output_type, target):
        try:
            entry = data["outputs"][output_type][target]
        except (KeyError, TypeError):
            raise KeyError("destination not found") from None
        if not isinstance(entry, dict):
            raise ValueError("destination configuration must be an object")
        return entry

    def _find_route(self, data, key):
        wanted = key.split(":", 1)[1]
        for source, position, entry in self._route_entries(data):
            current = str(entry.get("id") or f"legacy-{source}-{position}")
            if current == wanted:
                return source, position, entry
        raise KeyError("route not found")

    @staticmethod
    def _remove_route_position(data, source, position):
        section = data.get("routing", {}).get(source)
        if not isinstance(section, dict):
            raise KeyError("route not found")
        entries = section.get("outputs")
        if not isinstance(entries, list) or not 0 <= position < len(entries):
            raise KeyError("route not found")
        entries.pop(position)
        if not entries:
            data["routing"].pop(source, None)

    def _destination_id_for_entry(self, entry):
        key = f"destination:{str(entry.get('output')).casefold()}:{entry.get('target', 'default')}"
        return self._destination_by_key(key).id

    def _new_target(self, display, output_type, *, data=None):
        base = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(display).strip()).strip("_.-").casefold()
        if not base:
            base = output_type
        base = base[:64]
        candidate = base
        existing = set()
        source = data if data is not None else self.config_service.snapshot()
        group = source.get("outputs", {}).get(output_type, {})
        if isinstance(group, dict):
            existing = {str(key) for key in group if key != "enabled"}
        position = 2
        while candidate in existing:
            candidate = f"{base[:72]}_{position}"
            position += 1
        if not _TARGET.fullmatch(candidate):
            raise ValueError("destination target is invalid")
        return candidate

    @staticmethod
    def _decode(source):
        import yaml

        try:
            value = yaml.safe_load(source) or {}
        except yaml.YAMLError as error:
            raise ValueError("mounted YAML configuration is invalid") from error
        if not isinstance(value, dict):
            raise ValueError("mounted YAML configuration root must be an object")
        return value

    @staticmethod
    def _require_admin(actor):
        if not actor.is_admin:
            raise PermissionError("administrator access is required")

    def _audit(self, actor, action, outcome, details=None):
        self.audit.write(actor, action, "configuration", None, outcome, details)
