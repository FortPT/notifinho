"""Migrate legacy YAML resources into isolated database-authoritative stores."""

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
from api.security import TokenAuthenticator, hash_token
from integrations.catalog import canonical_source, infer_input_type
from outputs.settings import OUTPUT_TYPES, normalize_output_settings
from storage.api_tokens import APITokenStore
from storage.audit_events import AuditEventStore
from storage.destinations import DestinationStore
from storage.ownership import Actor
from storage.routes import RouteStore, route_priority_name, route_priority_value
from storage.secrets import SecretStore
from storage.integrations import IntegrationCategoryStore
from storage.settings import (
    DEFAULT_BACKUP_SETTINGS,
    DEFAULT_INTEGRATION_SETTINGS,
    DEFAULT_REGIONAL_SETTINGS,
    SettingsStore,
    runtime_overlay_status,
)
from storage.validation import ConflictError, normalized_name


LEGACY_CONFIGURATION_MODEL = "unified_yaml_v1"
CONFIGURATION_MODEL = "platform_database_v1"
_SYNC_LOCK = threading.RLock()
_TARGET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
_ROUTE_ID = re.compile(r"^[0-9a-f]{12,32}$")
_SOURCE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,79}$")
_SOURCE_CATEGORY_ALIASES = {
    "servers": "hardware",
    "services": "monitoring",
    "applications": "generic",
    "controllers": "networking",
}
_SOURCE_CATEGORIES = {
    "virtualization",
    "monitoring",
    "storage",
    "networking",
    "hardware",
    "automation",
    "containers",
    "security",
    "generic",
}
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
    """Perform one-way YAML migration and maintain runtime settings overlays.

    In ``platform_database_v1`` mode, destinations, routes, API tokens, regional
    preferences, backup schedules, aliases, and integration behavior live in
    isolated SQLite records. ``config.yaml`` contains only process bootstrap and
    listener settings.
    """

    def __init__(self, config_service, database, *, audit=None):
        self.config_service = config_service
        self.database = database
        self.audit = audit or AuditEventStore(database)
        self.secrets = SecretStore(database)
        self.tokens = APITokenStore(database, audit=self.audit)
        self.settings = SettingsStore(database, audit=self.audit)
        self.integration_categories = IntegrationCategoryStore(database)
        self._fingerprint = ""

    @property
    def database_authoritative(self) -> bool:
        return str(
            self.config_service.configuration.get(
                "platform",
                "configuration_model",
                default="",
            )
            or ""
        ).strip().casefold() == CONFIGURATION_MODEL

    def synchronize(self, *, force: bool = False) -> ConfigurationSyncStatus:
        """Migrate legacy YAML once, then only refresh the runtime overlay."""

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

            owner_id = self._configuration_owner()
            fingerprint = hashlib.sha256(source.encode("utf-8")).hexdigest()
            platform = data.get("platform") if isinstance(data.get("platform"), dict) else {}
            model = str(platform.get("configuration_model") or "").strip().casefold()

            if model == CONFIGURATION_MODEL:
                overlay_errors = self._apply_runtime_overlay()
                changed = force or fingerprint != self._fingerprint
                self._fingerprint = fingerprint
                return ConfigurationSyncStatus(
                    True,
                    changed,
                    fingerprint,
                    owner_id,
                    tuple(
                        f"{item['namespace']}.{item['resource']}: {item['message']}"
                        for item in overlay_errors
                    ),
                )

            if model not in {"", LEGACY_CONFIGURATION_MODEL}:
                return ConfigurationSyncStatus(
                    False,
                    False,
                    fingerprint,
                    owner_id,
                    (f"unsupported configuration model: {model}",),
                )

            if owner_id is None:
                return ConfigurationSyncStatus(
                    False,
                    False,
                    fingerprint,
                    None,
                    ("create the first administrator before resource migration",),
                )

            actor = Actor(owner_id, "admin")
            try:
                candidate = deepcopy(data)
                self._migrate_integration_model(candidate)
                changed = self._synchronize_data(actor, candidate, remove_stale=True)
                imported_tokens = self._import_legacy_tokens(actor, candidate)
                imported_settings = self._import_legacy_settings(candidate)
                normalized = self._database_core_configuration(candidate)
                with self.database.transaction() as connection:
                    connection.execute(
                        "UPDATE destinations SET configuration_key = NULL "
                        "WHERE configuration_key IS NOT NULL"
                    )
                    connection.execute(
                        "UPDATE routes SET configuration_key = NULL "
                        "WHERE configuration_key IS NOT NULL"
                    )
                self.config_service.replace(normalized)
                self._apply_runtime_overlay()
                source = self.config_service.source_text()
                fingerprint = hashlib.sha256(source.encode("utf-8")).hexdigest()
                self._fingerprint = fingerprint
                self._audit(
                    actor,
                    "configuration.database_migrate",
                    "success",
                    {
                        "tokens_imported": imported_tokens,
                        "settings_imported": imported_settings,
                    },
                )
                return ConfigurationSyncStatus(
                    True,
                    True,
                    fingerprint,
                    owner_id,
                )
            except Exception as error:
                return ConfigurationSyncStatus(
                    False,
                    False,
                    fingerprint,
                    owner_id,
                    (f"resource migration failed: {error}",),
                )

    def list_destinations(self, actor: Actor) -> list:
        self.synchronize()
        return DestinationStore(self.database).list_visible(actor)

    def list_routes(self, actor: Actor) -> list:
        self.synchronize()
        return RouteStore(self.database).list_visible(actor)

    def create_destination(self, actor: Actor, data: dict):
        self._require_admin(actor)
        self._ready()
        output_type = str(data.get("output_type") or "").strip().casefold()
        if output_type not in OUTPUT_TYPES:
            raise ValueError("unsupported destination output type")
        display, _normalized = normalized_name(data.get("name"), "destination name")
        settings = normalize_output_settings(output_type, data.get("settings", {}))
        enabled = self._boolean(data.get("enabled", True), "enabled")
        shared = self._boolean(data.get("shared", True), "shared")
        secret = data.get("secret")
        original = self.config_service.snapshot()
        candidate = deepcopy(original)
        self._assert_destination_name_available(candidate, display)
        target = self._new_target(display, output_type, data=candidate)
        group = candidate.setdefault("outputs", {}).setdefault(output_type, {})
        if not isinstance(group, dict):
            raise ValueError("output group must be an object")
        if enabled:
            group["enabled"] = True
        else:
            group.setdefault("enabled", True)
        group[target] = self._destination_entry(
            output_type,
            display,
            settings,
            enabled,
            secret,
            shared,
        )
        self._replace_and_synchronize(original, candidate)
        item = self._destination_by_key(f"destination:{output_type}:{target}")
        self._audit(actor, "destination.create", "success", {"target": target})
        return item

    def update_destination(self, actor: Actor, destination_id: str, data: dict):
        self._require_admin(actor)
        self._ready()
        output_type, target = self._destination_location(destination_id)
        original = self.config_service.snapshot()
        candidate = deepcopy(original)
        entry = self._destination_yaml(candidate, output_type, target)
        current = self._parse_destination(output_type, target, entry)
        next_type = str(data.get("output_type") or output_type).strip().casefold()
        if next_type not in OUTPUT_TYPES:
            raise ValueError("unsupported destination output type")
        display, _normalized = normalized_name(
            data.get("name", current["name"]),
            "destination name",
        )
        self._assert_destination_name_available(
            candidate,
            display,
            excluding=(output_type, target),
        )
        if "settings" in data:
            settings = normalize_output_settings(next_type, data["settings"])
        elif next_type == output_type:
            settings = current["settings"]
        else:
            raise ValueError(
                "destination settings are required when changing destination type"
            )
        enabled = (
            self._boolean(data["enabled"], "enabled")
            if "enabled" in data
            else current["enabled"]
        )
        shared = (
            self._boolean(data["shared"], "shared")
            if "shared" in data
            else current["shared"]
        )
        if "secret" in data:
            secret = data["secret"]
        elif next_type == output_type:
            secret = current["secret_value"]
        else:
            raise ValueError(
                "new credentials are required when changing destination type"
            )

        next_target = target
        rebind = None
        if next_type != output_type:
            next_target = self._new_target(display, next_type, data=candidate)
            del candidate["outputs"][output_type][target]
            old_group = candidate["outputs"][output_type]
            if not [key for key in old_group if key != "enabled"]:
                candidate["outputs"].pop(output_type, None)
            self._update_route_destination_refs(
                candidate,
                output_type,
                target,
                next_type,
                next_target,
            )
            rebind = (
                destination_id,
                f"destination:{output_type}:{target}",
                f"destination:{next_type}:{next_target}",
            )

        group = candidate.setdefault("outputs", {}).setdefault(next_type, {})
        if not isinstance(group, dict):
            raise ValueError("output group must be an object")
        if enabled:
            group["enabled"] = True
        else:
            group.setdefault("enabled", True)
        group[next_target] = self._destination_entry(
            next_type,
            display,
            settings,
            enabled,
            secret,
            shared,
        )
        self._replace_and_synchronize(
            original,
            candidate,
            rebind_destination=rebind,
        )
        self._audit(actor, "destination.update", "success", {"target": next_target})
        return self._destination_by_key(
            f"destination:{next_type}:{next_target}"
        )

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
        input_type = RouteStore._input_type(data.get("input_type"))
        destination_type, target = self._destination_location(data.get("destination_id"))
        display, _normalized = normalized_name(data.get("name"), "route name")
        filters = self._decoded_filters(data.get("filters", {}))
        priority = self._priority(data.get("priority", 100))
        enabled = self._boolean(data.get("enabled", True), "enabled")
        route_key = uuid.uuid4().hex[:16]
        original = self.config_service.snapshot()
        candidate = deepcopy(original)
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
                input_type,
                filters,
                priority,
                enabled,
            )
        )
        self._replace_and_synchronize(original, candidate)
        self._audit(actor, "route.create", "success", {"source": source})
        return self._route_by_key(f"route:{route_key}")

    def update_route(self, actor: Actor, route_id: str, data: dict):
        self._require_admin(actor)
        self._ready()
        key = self._route_configuration_key(route_id)
        original = self.config_service.snapshot()
        candidate = deepcopy(original)
        source, position, entry = self._find_route(candidate, key)
        next_source = RouteStore._source(data.get("source", source))
        input_type = RouteStore._input_type(
            data.get("input_type", entry.get("input", ""))
        )
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
            input_type,
            filters,
            priority,
            enabled,
        )
        self._remove_route_position(candidate, source, position)
        candidate.setdefault("routing", {}).setdefault(
            next_source,
            {"outputs": []},
        ).setdefault("outputs", []).append(replacement)
        self._replace_and_synchronize(original, candidate)
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
        if self.database_authoritative:
            return []
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
        values, _error = self.settings.get_safe(
            "platform",
            "regional",
            DEFAULT_REGIONAL_SETTINGS,
        )
        return values

    def update_preferences(self, actor: Actor, values: dict) -> dict:
        self._require_admin(actor)
        self._ready()
        record = self.settings.set(actor, "platform", "regional", values)
        self._apply_runtime_overlay()
        return record.value

    def source_categories(self) -> dict[str, str]:
        self.synchronize()
        return self.integration_categories.list_overrides()

    def removed_sources(self) -> list[str]:
        self.synchronize()
        return []

    def update_source_category(
        self,
        actor: Actor,
        source: str,
        category: str,
    ) -> dict[str, str]:
        self._require_admin(actor)
        self._ready()
        self.integration_categories.set_category(source, category)
        self._audit(
            actor,
            "integration.category.update",
            "success",
            {"source": canonical_source(source), "category": category},
        )
        return self.integration_categories.list_overrides()

    def remove_source(self, actor: Actor, source: str) -> None:
        self._require_admin(actor)
        raise ValueError("built-in integrations cannot be removed")

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
        values, _error = self.settings.get_safe(
            "platform",
            "backups",
            DEFAULT_BACKUP_SETTINGS,
        )
        return values

    def update_backup_settings(self, actor: Actor, values: dict) -> dict:
        self._require_admin(actor)
        self._ready()
        record = self.settings.set(actor, "platform", "backups", values)
        self._apply_runtime_overlay()
        return record.value

    def integration_settings(self) -> dict:
        self.synchronize()
        values = {}
        errors = []
        for key, default in DEFAULT_INTEGRATION_SETTINGS.items():
            try:
                values[key] = self.settings.get("integration", key, default)
            except Exception as error:
                values[key] = deepcopy(default)
                errors.append(
                    {
                        "resource": key,
                        "code": "integration_settings_unavailable",
                        "message": str(error),
                    }
                )
        return {"settings": values, "errors": errors}

    def update_integration_settings(
        self,
        actor: Actor,
        source: str,
        values: dict,
    ) -> dict:
        self._require_admin(actor)
        self._ready()
        key = str(source or "").strip().casefold()
        record = self.settings.set(actor, "integration", key, values)
        self._apply_runtime_overlay()
        return record.value

    def adopt_unmanaged_resources(self, actor: Actor) -> int:
        """Compatibility no-op after the one-way database migration."""

        self._require_admin(actor)
        if self.database_authoritative:
            return 0
        with _SYNC_LOCK:
            candidate = self.config_service.snapshot()
            adopted = self._adopt_unmanaged(candidate, actor)
            if adopted:
                candidate.setdefault("platform", {})["configuration_model"] = CONFIGURATION_MODEL
                candidate["platform"].pop("routing_authority", None)
                self.config_service.replace(candidate)
                self.synchronize(force=True)
            return adopted

    def _import_legacy_tokens(self, actor: Actor, data: dict) -> int:
        api = data.get("api") if isinstance(data.get("api"), dict) else {}
        tokens = api.get("tokens") if isinstance(api, dict) else {}
        if not isinstance(tokens, dict):
            return 0
        imported = 0
        for name, values in tokens.items():
            if not isinstance(values, dict):
                continue
            enabled = values.get("enabled", True) is True
            digest = TokenAuthenticator._expected_hash(values)
            if not digest:
                if enabled:
                    raise ValueError(
                        f"api token {name} cannot be imported because its credential is unavailable"
                    )
                digest = hash_token(f"disabled-legacy-{name}-{uuid.uuid4().hex}")
            display_name = str(name)
            try:
                self.tokens.import_legacy_hash(
                    actor,
                    actor.user_id,
                    display_name,
                    digest,
                    source_scopes=values.get("sources", []),
                    role=values.get("role", "application"),
                    rate_limit_per_minute=values.get("rate_limit_per_minute", 60),
                    enabled=enabled,
                )
            except ValueError as error:
                if "application with this name already exists" not in str(error):
                    raise
                display_name = self._available_legacy_token_name(actor.user_id, display_name)
                self.tokens.import_legacy_hash(
                    actor,
                    actor.user_id,
                    display_name,
                    digest,
                    source_scopes=values.get("sources", []),
                    role=values.get("role", "application"),
                    rate_limit_per_minute=values.get("rate_limit_per_minute", 60),
                    enabled=enabled,
                )
            imported += 1
        return imported

    def _available_legacy_token_name(self, owner_user_id: str, name: str) -> str:
        base = f"Legacy {str(name or '').strip()}".strip()
        for index in range(1, 1000):
            candidate = base if index == 1 else f"{base} {index}"
            _display, normalized = normalized_name(candidate, "token name")
            with self.database.connect() as connection:
                exists = connection.execute(
                    """
                    SELECT 1 FROM api_tokens
                    WHERE owner_user_id = ? AND name_normalized = ?
                    """,
                    (str(owner_user_id), normalized),
                ).fetchone()
            if exists is None:
                return candidate
        raise ValueError("a unique legacy token name could not be allocated")

    def _import_legacy_settings(self, data: dict) -> int:
        imported = 0
        presentation = data.get("presentation")
        presentation = presentation if isinstance(presentation, dict) else {}
        webui = data.get("webui")
        webui = webui if isinstance(webui, dict) else {}
        regional = {
            "timezone": str(
                presentation.get("timezone")
                or DEFAULT_REGIONAL_SETTINGS["timezone"]
            ),
            "language": str(
                webui.get("language")
                or DEFAULT_REGIONAL_SETTINGS["language"]
            ),
            "time_format": str(
                presentation.get("time_format")
                or DEFAULT_REGIONAL_SETTINGS["time_format"]
            ),
        }
        imported += int(
            self.settings.import_if_missing("platform", "regional", regional)
        )

        platform = data.get("platform")
        platform = platform if isinstance(platform, dict) else {}
        backups = platform.get("backups")
        if not isinstance(backups, dict):
            backups = deepcopy(DEFAULT_BACKUP_SETTINGS)
        else:
            backups = {**DEFAULT_BACKUP_SETTINGS, **backups}
        imported += int(
            self.settings.import_if_missing("platform", "backups", backups)
        )

        notifications = data.get("notifications")
        notifications = notifications if isinstance(notifications, dict) else {}
        for key in ("xo", "zabbix", "dell_idrac", "unifi_protect"):
            value = notifications.get(key)
            if not isinstance(value, dict):
                value = deepcopy(DEFAULT_INTEGRATION_SETTINGS[key])
            else:
                value = {**DEFAULT_INTEGRATION_SETTINGS[key], **value}
            imported += int(
                self.settings.import_if_missing("integration", key, value)
            )

        home_assistant_section = data.get("home_assistant")
        if not isinstance(home_assistant_section, dict):
            home_assistant = deepcopy(DEFAULT_INTEGRATION_SETTINGS["home_assistant"])
        else:
            home_assistant = {
                "aliases": deepcopy(home_assistant_section.get("aliases") or {})
            }
        imported += int(
            self.settings.import_if_missing(
                "integration", "home_assistant", home_assistant
            )
        )

        redfish_section = data.get("redfish")
        if not isinstance(redfish_section, dict):
            redfish = deepcopy(DEFAULT_INTEGRATION_SETTINGS["redfish"])
        else:
            redfish = {
                "deduplication_window_seconds": redfish_section.get(
                    "deduplication_window_seconds",
                    DEFAULT_INTEGRATION_SETTINGS["redfish"][
                        "deduplication_window_seconds"
                    ],
                )
            }
        imported += int(
            self.settings.import_if_missing("integration", "redfish", redfish)
        )
        return imported

    def _database_core_configuration(self, data: dict) -> dict:
        candidate = deepcopy(data)
        for key in (
            "outputs",
            "routing",
            "notifications",
            "presentation",
            "home_assistant",
            "redfish",
        ):
            candidate.pop(key, None)

        api = candidate.get("api")
        if isinstance(api, dict):
            api.pop("tokens", None)

        platform = candidate.setdefault("platform", {})
        if not isinstance(platform, dict):
            raise ValueError("platform must be an object")
        platform["configuration_model"] = CONFIGURATION_MODEL
        platform.pop("routing_authority", None)
        platform.pop("backups", None)

        webui = candidate.get("webui")
        if isinstance(webui, dict):
            webui.pop("language", None)
            webui.pop("source_categories", None)
            webui.pop("removed_sources", None)

        errors = validate_config(candidate)
        if errors:
            raise ValueError("; ".join(errors))
        return candidate

    def _apply_runtime_overlay(self) -> list[dict]:
        overlay, errors = runtime_overlay_status(self.settings)
        apply = getattr(
            self.config_service.configuration,
            "apply_runtime_overlay",
            None,
        )
        if callable(apply):
            apply(overlay)
        return errors

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
        display, normalized = normalized_name(spec["name"], "route name")
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
            if row is None:
                # Integration migration can canonicalize a legacy source such
                # as ``generic`` to ``*``. Route names are unique per owner, so
                # this safely adopts the existing row instead of inserting a
                # duplicate during the same synchronization pass.
                row = connection.execute(
                    """
                    SELECT * FROM routes
                    WHERE configuration_key IS NULL AND owner_user_id = ?
                      AND name_normalized = ?
                    ORDER BY priority, created_at LIMIT 1
                    """,
                    (actor.user_id, normalized),
                ).fetchone()
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
                        source, input_type, filters_json, priority, enabled,
                        created_at, updated_at, configuration_key
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        route_id,
                        actor.user_id,
                        spec["destination_id"],
                        display,
                        normalized,
                        source,
                        spec["input_type"],
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
                        name_normalized = ?, source = ?, input_type = ?,
                        filters_json = ?, priority = ?, enabled = ?,
                        updated_at = ?, configuration_key = ?
                    WHERE id = ?
                    """,
                    (
                        actor.user_id,
                        spec["destination_id"],
                        display,
                        normalized,
                        source,
                        spec["input_type"],
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
                        str(row["input_type"] or "") if "input_type" in row.keys() else "",
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
                "source": canonical_source(source),
                "input_type": RouteStore._input_type(entry.get("input", "")),
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
    def _route_entry(
        route_key,
        name,
        output_type,
        target,
        input_type,
        filters,
        priority,
        enabled,
    ):
        entry = {
            "id": route_key,
            "name": name,
            "output": output_type,
            "target": target,
            "priority": route_priority_name(priority),
            "enabled": bool(enabled),
        }
        if input_type:
            entry["input"] = input_type
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

    def _migrate_integration_model(self, candidate: dict) -> bool:
        changed = False
        webui = candidate.get("webui")
        if isinstance(webui, dict):
            legacy_categories = webui.pop("source_categories", None)
            if legacy_categories is not None:
                self.integration_categories.import_legacy(legacy_categories)
                changed = True
            if "removed_sources" in webui:
                webui.pop("removed_sources", None)
                changed = True

        routing = candidate.get("routing")
        if not isinstance(routing, dict):
            return changed

        rebuilt = {}
        for source, section in routing.items():
            if not isinstance(section, dict):
                rebuilt[source] = section
                continue
            entries = section.get("outputs")
            legacy_single = entries is None
            if entries is None:
                entries = [section]
            if not isinstance(entries, list):
                rebuilt[source] = section
                continue

            canonical = canonical_source(source)
            next_source = canonical
            if canonical in {"generic", "redfish", "restful", "rest_api", "home_lab"}:
                next_source = "*"

            kept = []
            for entry in entries:
                if not isinstance(entry, dict):
                    kept.append(entry)
                    continue
                name = " ".join(str(entry.get("name") or "").split()).casefold()
                if name == "home lab generic":
                    changed = True
                    continue
                next_entry = deepcopy(entry)
                if not str(next_entry.get("input") or "").strip():
                    inferred = infer_input_type(source)
                    if inferred:
                        next_entry["input"] = inferred
                        changed = True
                kept.append(next_entry)

            if not kept:
                changed = True
                continue
            if next_source != source:
                changed = True
            target = rebuilt.setdefault(next_source, {"outputs": []})
            if not isinstance(target, dict):
                target = {"outputs": []}
                rebuilt[next_source] = target
            target_entries = target.setdefault("outputs", [])
            if not isinstance(target_entries, list):
                target_entries = []
                target["outputs"] = target_entries
            target_entries.extend(kept)
            if legacy_single:
                changed = True

        if rebuilt != routing:
            candidate["routing"] = rebuilt
            changed = True
        return changed

    def _assert_destination_name_available(
        self,
        data: dict,
        display: str,
        *,
        excluding: tuple[str, str] | None = None,
    ) -> None:
        wanted = normalized_name(display, "destination name")[1]
        outputs = data.get("outputs") or {}
        for output_type, group in outputs.items():
            if not isinstance(group, dict):
                continue
            for target, entry in group.items():
                if target == "enabled" or not isinstance(entry, dict):
                    continue
                if excluding == (str(output_type), str(target)):
                    continue
                current = normalized_name(
                    entry.get("name") or target,
                    "destination name",
                )[1]
                if current == wanted:
                    raise ConflictError(
                        f'A destination named "{display}" already exists. '
                        "Choose another name."
                    )

    def _replace_and_synchronize(
        self,
        original: dict,
        candidate: dict,
        *,
        rebind_destination=None,
    ) -> None:
        rebound = False
        try:
            self.config_service.replace(candidate)
            if rebind_destination is not None:
                destination_id, old_key, new_key = rebind_destination
                with self.database.transaction() as connection:
                    updated = connection.execute(
                        """
                        UPDATE destinations SET configuration_key = ?
                        WHERE id = ? AND configuration_key = ?
                        """,
                        (new_key, destination_id, old_key),
                    ).rowcount
                if updated != 1:
                    raise KeyError("destination could not be rebound")
                rebound = True
            status = self.synchronize(force=True)
            if not status.ready:
                raise ValueError(
                    "; ".join(status.errors)
                    or "configuration synchronization failed"
                )
        except Exception:
            if rebound and rebind_destination is not None:
                destination_id, old_key, new_key = rebind_destination
                with self.database.transaction() as connection:
                    connection.execute(
                        """
                        UPDATE destinations SET configuration_key = ?
                        WHERE id = ? AND configuration_key = ?
                        """,
                        (old_key, destination_id, new_key),
                    )
            self.config_service.replace(original)
            rollback = self.synchronize(force=True)
            if not rollback.ready:
                raise RuntimeError(
                    "configuration rollback requires operator attention"
                )
            raise

    @staticmethod
    def _update_route_destination_refs(
        data: dict,
        old_type: str,
        old_target: str,
        new_type: str,
        new_target: str,
    ) -> None:
        for _source, _position, entry in UnifiedConfigurationService._route_entries(data):
            if (
                str(entry.get("output") or "").casefold() == old_type
                and str(entry.get("target", "default")) == old_target
            ):
                entry["output"] = new_type
                entry["target"] = new_target

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
