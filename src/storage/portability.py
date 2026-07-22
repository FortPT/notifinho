"""Validated, preview-first platform export and v1 YAML migration."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import unicodedata

from dataclasses import dataclass

import yaml

from outputs.settings import normalize_output_settings, validate_public_https_url
from storage.audit_events import AuditEventStore
from storage.database import Database
from storage.destinations import DestinationStore
from storage.ownership import Actor
from storage.routes import RouteStore
from storage.secrets import SecretStore
from storage.validation import normalized_name


PORTABLE_SCHEMA = "notifinho.platform.v1"
MAXIMUM_DOCUMENT_BYTES = 1024 * 1024
MAXIMUM_DESTINATIONS = 500
MAXIMUM_ROUTES = 1000


@dataclass(frozen=True)
class ImportPlan:
    kind: str
    fingerprint: str
    destinations: tuple[dict, ...]
    routes: tuple[dict, ...]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.errors

    def public(self) -> dict:
        return {
            "kind": self.kind,
            "fingerprint": self.fingerprint,
            "valid": self.valid,
            "destinations": [
                {
                    "ref": item["ref"],
                    "owner": item["owner"],
                    "name": item["name"],
                    "output_type": item["output_type"],
                    "shared": item["shared"],
                    "enabled": item["enabled"],
                    "secret_present": bool(item.get("secret_value")),
                    "secret_required": bool(item.get("secret_required")),
                }
                for item in self.destinations
            ],
            "routes": [
                {
                    "owner": item["owner"],
                    "name": item["name"],
                    "source": item["source"],
                    "destination_ref": item["destination_ref"],
                    "enabled": item["enabled"],
                }
                for item in self.routes
            ],
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "summary": {
                "destinations": len(self.destinations),
                "routes": len(self.routes),
            },
        }


class PlatformPortabilityService:
    """Export safe metadata and import only after an unchanged preview."""

    def __init__(
        self,
        database: Database,
        *,
        secrets: SecretStore | None = None,
        audit: AuditEventStore | None = None,
        clock=time.time,
    ):
        self.database = database
        self.secrets = secrets or SecretStore(database)
        self.audit = audit
        self.clock = clock
        self.destinations = DestinationStore(database, audit=audit)
        self.routes = RouteStore(database, audit=audit)

    def export_document(self, actor: Actor) -> dict:
        self._require_admin(actor)
        with self.database.connect() as connection:
            destination_rows = connection.execute(
                """
                SELECT destinations.*, users.username AS owner_username
                FROM destinations
                JOIN users ON users.id = destinations.owner_user_id
                ORDER BY users.username_normalized, destinations.name_normalized
                """
            ).fetchall()
            route_rows = connection.execute(
                """
                SELECT routes.*, users.username AS owner_username
                FROM routes
                JOIN users ON users.id = routes.owner_user_id
                ORDER BY users.username_normalized, routes.priority,
                         routes.name_normalized
                """
            ).fetchall()
        references = {
            str(row["id"]): f"destination-{index}"
            for index, row in enumerate(destination_rows, start=1)
        }
        document = {
            "schema": PORTABLE_SCHEMA,
            "exported_at": int(self.clock()),
            "destinations": [
                {
                    "ref": references[str(row["id"])],
                    "owner": str(row["owner_username"]),
                    "name": str(row["name"]),
                    "output_type": str(row["output_type"]),
                    "settings": json.loads(str(row["settings_json"])),
                    "shared": bool(row["shared"]),
                    "enabled": bool(row["enabled"]),
                    "secret_required": row["secret_id"] is not None,
                }
                for row in destination_rows
            ],
            "routes": [
                {
                    "owner": str(row["owner_username"]),
                    "name": str(row["name"]),
                    "source": str(row["source"]),
                    "destination_ref": references[str(row["destination_id"])],
                    "filters": json.loads(str(row["filters_json"])),
                    "priority": int(row["priority"]),
                    "enabled": bool(row["enabled"]),
                }
                for row in route_rows
            ],
        }
        self._audit(actor, "portability.export", "success", {
            "destinations": len(destination_rows),
            "routes": len(route_rows),
            "secrets_exported": False,
        })
        return document

    def preview_document(self, actor: Actor, document) -> ImportPlan:
        self._require_admin(actor)
        fingerprint, decoded, size_error = self._json_document(document)
        if size_error:
            return ImportPlan("portable", fingerprint, (), (), (), (size_error,))
        errors: list[str] = []
        warnings: list[str] = []
        destinations: list[dict] = []
        routes: list[dict] = []
        if not isinstance(decoded, dict) or decoded.get("schema") != PORTABLE_SCHEMA:
            return ImportPlan(
                "portable",
                fingerprint,
                (),
                (),
                (),
                (f"document schema must be {PORTABLE_SCHEMA}",),
            )
        raw_destinations = decoded.get("destinations", [])
        raw_routes = decoded.get("routes", [])
        if not isinstance(raw_destinations, list):
            errors.append("destinations must be a list")
            raw_destinations = []
        if not isinstance(raw_routes, list):
            errors.append("routes must be a list")
            raw_routes = []
        if len(raw_destinations) > MAXIMUM_DESTINATIONS:
            errors.append(f"destinations must not exceed {MAXIMUM_DESTINATIONS}")
            raw_destinations = []
        if len(raw_routes) > MAXIMUM_ROUTES:
            errors.append(f"routes must not exceed {MAXIMUM_ROUTES}")
            raw_routes = []

        users = self._users()
        existing_destinations, existing_routes = self._existing_names()
        planned_destination_names = set(existing_destinations)
        planned_route_names = set(existing_routes)
        references: dict[str, dict] = {}
        for index, raw in enumerate(raw_destinations, start=1):
            label = f"destination {index}"
            try:
                item = self._portable_destination(raw, users)
                if item["ref"] in references:
                    raise ValueError("destination reference is duplicated")
                key = (item["owner_id"], item["name_normalized"])
                if key in planned_destination_names:
                    raise ValueError("destination name already exists for this owner")
                planned_destination_names.add(key)
                references[item["ref"]] = item
                destinations.append(item)
                if item["secret_required"]:
                    warnings.append(
                        f"{item['name']}: credential was intentionally not exported; "
                        "destination will be imported disabled"
                    )
            except (TypeError, ValueError) as error:
                errors.append(f"{label}: {error}")

        for index, raw in enumerate(raw_routes, start=1):
            label = f"route {index}"
            try:
                item = self._portable_route(raw, users, references)
                key = (item["owner_id"], item["name_normalized"])
                if key in planned_route_names:
                    raise ValueError("route name already exists for this owner")
                planned_route_names.add(key)
                routes.append(item)
            except (KeyError, TypeError, ValueError) as error:
                errors.append(f"{label}: {error}")
        return ImportPlan(
            "portable",
            fingerprint,
            tuple(destinations),
            tuple(routes),
            tuple(warnings),
            tuple(errors),
        )

    def preview_v1_yaml(self, actor: Actor, source: str) -> ImportPlan:
        self._require_admin(actor)
        raw = str(source or "")
        encoded = raw.encode("utf-8")
        fingerprint = hashlib.sha256(encoded).hexdigest()
        if not encoded or len(encoded) > MAXIMUM_DOCUMENT_BYTES:
            message = "YAML document must contain 1 to 1048576 bytes"
            return ImportPlan("v1_yaml", fingerprint, (), (), (), (message,))
        try:
            decoded = yaml.safe_load(raw)
        except yaml.YAMLError:
            return ImportPlan(
                "v1_yaml", fingerprint, (), (), (), ("YAML document is invalid",)
            )
        if not isinstance(decoded, dict):
            return ImportPlan(
                "v1_yaml", fingerprint, (), (), (), ("YAML root must be an object",)
            )
        users = self._users()
        admin_name = users[actor.user_id]["username"]
        existing_destinations, existing_routes = self._existing_names()
        planned_destination_names = set(existing_destinations)
        planned_route_names = set(existing_routes)
        errors: list[str] = []
        warnings: list[str] = []
        destinations: list[dict] = []
        routes: list[dict] = []
        references: dict[tuple[str, str], dict] = {}
        outputs = decoded.get("outputs") or {}
        if not isinstance(outputs, dict):
            errors.append("outputs must be an object")
            outputs = {}
        for output_type in ("discord", "teams"):
            group = outputs.get(output_type) or {}
            if not isinstance(group, dict):
                errors.append(f"outputs.{output_type} must be an object")
                continue
            group_enabled = group.get("enabled", True)
            if not isinstance(group_enabled, bool):
                errors.append(f"outputs.{output_type}.enabled must be a boolean")
                group_enabled = False
            for target, settings in group.items():
                if target == "enabled":
                    continue
                if not isinstance(settings, dict):
                    errors.append(f"outputs.{output_type}.{target} must be an object")
                    continue
                value = str(settings.get("webhook") or "").strip()
                if not value or "PASTE_" in value.upper():
                    warnings.append(
                        f"outputs.{output_type}.{target}: placeholder credential skipped"
                    )
                    continue
                try:
                    validate_public_https_url(value, f"{output_type} webhook")
                    display, normalized = normalized_name(
                        f"Imported {output_type} {target}",
                        "destination name",
                    )
                    key = (actor.user_id, normalized)
                    if key in planned_destination_names:
                        raise ValueError("destination name already exists")
                    planned_destination_names.add(key)
                    reference = f"{output_type}:{target}"
                    item = {
                        "ref": reference,
                        "owner": admin_name,
                        "owner_id": actor.user_id,
                        "name": display,
                        "name_normalized": normalized,
                        "output_type": output_type,
                        "settings": normalize_output_settings(output_type, {}),
                        "shared": True,
                        "enabled": group_enabled,
                        "secret_required": True,
                        "secret_value": value,
                    }
                    references[(output_type, str(target))] = item
                    destinations.append(item)
                except (TypeError, ValueError) as error:
                    errors.append(f"outputs.{output_type}.{target}: {error}")

        routing = decoded.get("routing") or {}
        if not isinstance(routing, dict):
            errors.append("routing must be an object")
            routing = {}
        for source_name, raw_route in routing.items():
            if not isinstance(raw_route, dict):
                errors.append(f"routing.{source_name} must be an object")
                continue
            entries = raw_route.get("outputs")
            if entries is None:
                entries = [raw_route]
            if not isinstance(entries, list):
                errors.append(f"routing.{source_name}.outputs must be a list")
                continue
            for position, entry in enumerate(entries, start=1):
                try:
                    if not isinstance(entry, dict):
                        raise ValueError("route must be an object")
                    output_type = str(entry.get("output") or "").casefold()
                    target = str(entry.get("target", "default"))
                    destination = references.get((output_type, target))
                    if destination is None:
                        warnings.append(
                            f"routing.{source_name} entry {position}: target was not "
                            "imported and route was skipped"
                        )
                        continue
                    filters = self._v1_filters(entry.get("match"))
                    display, normalized = normalized_name(
                        f"Imported {source_name} to {output_type} {target} {position}",
                        "route name",
                    )
                    key = (actor.user_id, normalized)
                    if key in planned_route_names:
                        raise ValueError("route name already exists")
                    planned_route_names.add(key)
                    source_value = RouteStore._source(source_name)
                    RouteStore._filters(filters)
                    routes.append({
                        "owner": admin_name,
                        "owner_id": actor.user_id,
                        "name": display,
                        "name_normalized": normalized,
                        "source": source_value,
                        "destination_ref": destination["ref"],
                        "filters": filters,
                        "priority": min(1000, 100 + position),
                        "enabled": bool(destination["enabled"]),
                    })
                except (TypeError, ValueError) as error:
                    errors.append(f"routing.{source_name} entry {position}: {error}")
        return ImportPlan(
            "v1_yaml",
            fingerprint,
            tuple(destinations),
            tuple(routes),
            tuple(warnings),
            tuple(errors),
        )

    def apply_document(
        self,
        actor: Actor,
        document,
        fingerprint: str,
    ) -> dict:
        with self.database.maintenance():
            plan = self.preview_document(actor, document)
            return self._apply(actor, plan, fingerprint)

    def apply_v1_yaml(
        self,
        actor: Actor,
        source: str,
        fingerprint: str,
    ) -> dict:
        with self.database.maintenance():
            plan = self.preview_v1_yaml(actor, source)
            return self._apply(actor, plan, fingerprint)

    def _apply(self, actor: Actor, plan: ImportPlan, fingerprint: str) -> dict:
        if not plan.valid:
            raise ValueError("import preview contains errors")
        if not fingerprint or not hmac.compare_digest(
            plan.fingerprint,
            str(fingerprint),
        ):
            raise ValueError("import fingerprint does not match the preview")
        with self.database.maintenance():
            return self._apply_plan(actor, plan)

    def _apply_plan(self, actor: Actor, plan: ImportPlan) -> dict:
        created_routes: list[str] = []
        created_destinations: list[str] = []
        created_secrets: list[str] = []
        references: dict[str, str] = {}
        try:
            for item in plan.destinations:
                secret_id = None
                if item.get("secret_value"):
                    metadata = self.secrets.create(
                        actor,
                        item["owner_id"],
                        f"{item['name']} credential",
                        f"{item['output_type']}_credential",
                        item["secret_value"],
                    )
                    secret_id = metadata.id
                    created_secrets.append(metadata.id)
                enabled = bool(item["enabled"] and not (
                    item.get("secret_required") and not secret_id
                ))
                destination = self.destinations.create(
                    actor,
                    item["owner_id"],
                    item["name"],
                    item["output_type"],
                    secret_id=secret_id,
                    settings=item["settings"],
                    shared=item["shared"],
                    enabled=enabled,
                )
                created_destinations.append(destination.id)
                references[item["ref"]] = destination.id
            for item in plan.routes:
                destination_id = references[item["destination_ref"]]
                destination = next(
                    value for value in plan.destinations
                    if value["ref"] == item["destination_ref"]
                )
                enabled = bool(item["enabled"] and not (
                    destination.get("secret_required")
                    and not destination.get("secret_value")
                ))
                route = self.routes.create(
                    actor,
                    item["owner_id"],
                    item["name"],
                    item["source"],
                    destination_id,
                    filters=item["filters"],
                    priority=item["priority"],
                    enabled=enabled,
                )
                created_routes.append(route.id)
        except Exception:
            for route_id in reversed(created_routes):
                try:
                    self.routes.delete(actor, route_id)
                except Exception:
                    pass
            for destination_id in reversed(created_destinations):
                try:
                    self.destinations.delete(actor, destination_id)
                except Exception:
                    pass
            for secret_id in reversed(created_secrets):
                try:
                    self.secrets.delete(actor, secret_id)
                except Exception:
                    pass
            self._audit(actor, f"portability.{plan.kind}.apply", "failed")
            raise
        result = {
            "kind": plan.kind,
            "destinations_created": len(created_destinations),
            "routes_created": len(created_routes),
            "warnings": list(plan.warnings),
        }
        self._audit(actor, f"portability.{plan.kind}.apply", "success", result)
        return result

    def _portable_destination(self, raw, users) -> dict:
        if not isinstance(raw, dict):
            raise ValueError("must be an object")
        allowed = {
            "ref", "owner", "name", "output_type", "settings", "shared",
            "enabled", "secret_required",
        }
        unknown = set(raw) - allowed
        if unknown:
            raise ValueError(f"unsupported field: {sorted(unknown)[0]}")
        reference = str(raw.get("ref") or "").strip()
        if not reference or len(reference) > 128:
            raise ValueError("reference must contain 1 to 128 characters")
        owner = str(raw.get("owner") or "").strip()
        owner_normalized = self._normalized_username(owner)
        owner_record = next(
            (value for value in users.values() if value["normalized"] == owner_normalized),
            None,
        )
        if owner_record is None:
            raise ValueError("owner does not exist on this instance")
        display, normalized = normalized_name(raw.get("name"), "destination name")
        output_type = str(raw.get("output_type") or "").strip().casefold()
        settings = normalize_output_settings(output_type, raw.get("settings") or {})
        shared = self._boolean(raw, "shared", False)
        enabled = self._boolean(raw, "enabled", True)
        required = self._boolean(raw, "secret_required", False)
        return {
            "ref": reference,
            "owner": owner_record["username"],
            "owner_id": owner_record["id"],
            "name": display,
            "name_normalized": normalized,
            "output_type": output_type,
            "settings": settings,
            "shared": shared,
            "enabled": enabled,
            "secret_required": required,
        }

    def _portable_route(self, raw, users, references) -> dict:
        if not isinstance(raw, dict):
            raise ValueError("must be an object")
        allowed = {
            "owner", "name", "source", "destination_ref", "filters",
            "priority", "enabled",
        }
        unknown = set(raw) - allowed
        if unknown:
            raise ValueError(f"unsupported field: {sorted(unknown)[0]}")
        owner = str(raw.get("owner") or "").strip()
        owner_normalized = self._normalized_username(owner)
        owner_record = next(
            (value for value in users.values() if value["normalized"] == owner_normalized),
            None,
        )
        if owner_record is None:
            raise ValueError("owner does not exist on this instance")
        display, normalized = normalized_name(raw.get("name"), "route name")
        reference = str(raw.get("destination_ref") or "")
        destination = references[reference]
        if (
            destination["owner_id"] != owner_record["id"]
            and not destination["shared"]
        ):
            raise ValueError("route destination must be owned or shared")
        source = RouteStore._source(raw.get("source"))
        filters = raw.get("filters") or {}
        RouteStore._filters(filters)
        priority = int(raw.get("priority", 100))
        if not 0 <= priority <= 1000:
            raise ValueError("route priority must be between 0 and 1000")
        return {
            "owner": owner_record["username"],
            "owner_id": owner_record["id"],
            "name": display,
            "name_normalized": normalized,
            "source": source,
            "destination_ref": reference,
            "filters": filters,
            "priority": priority,
            "enabled": self._boolean(raw, "enabled", True),
        }

    def _users(self) -> dict[str, dict]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT id, username, username_normalized FROM users"
            ).fetchall()
        return {
            str(row["id"]): {
                "id": str(row["id"]),
                "username": str(row["username"]),
                "normalized": str(row["username_normalized"]),
            }
            for row in rows
        }

    def _existing_names(self):
        with self.database.connect() as connection:
            destinations = {
                (str(row["owner_user_id"]), str(row["name_normalized"]))
                for row in connection.execute(
                    "SELECT owner_user_id, name_normalized FROM destinations"
                )
            }
            routes = {
                (str(row["owner_user_id"]), str(row["name_normalized"]))
                for row in connection.execute(
                    "SELECT owner_user_id, name_normalized FROM routes"
                )
            }
        return destinations, routes

    @staticmethod
    def _json_document(document):
        try:
            encoded = json.dumps(
                document,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError):
            return "", None, "document must contain JSON values"
        fingerprint = hashlib.sha256(encoded).hexdigest()
        if not encoded or len(encoded) > MAXIMUM_DOCUMENT_BYTES:
            return fingerprint, None, "document must not exceed 1048576 bytes"
        return fingerprint, document, None

    @staticmethod
    def _boolean(value, key, default):
        item = value.get(key, default)
        if not isinstance(item, bool):
            raise ValueError(f"{key} must be a boolean")
        return item

    @staticmethod
    def _v1_filters(value) -> dict:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("match must be an object")
        unknown = set(value) - {"hosts"}
        if unknown:
            raise ValueError(f"unsupported v1 match field: {sorted(unknown)[0]}")
        hosts = value.get("hosts")
        if hosts is None:
            return {}
        return {"hosts": hosts if isinstance(hosts, list) else [hosts]}

    @staticmethod
    def _normalized_username(value: str) -> str:
        return unicodedata.normalize("NFKC", str(value or "")).strip().casefold()

    @staticmethod
    def _require_admin(actor: Actor) -> None:
        if not actor.is_admin:
            raise PermissionError("administrator role is required")

    def _audit(self, actor, action, outcome, details=None):
        if self.audit is not None:
            self.audit.write(actor, action, "platform_state", None, outcome, details)
