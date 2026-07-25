"""Server-side bridge between mounted YAML configuration and platform state."""

from __future__ import annotations

import hashlib
import hmac
import threading

from copy import deepcopy

import yaml

from storage.audit_events import AuditEventStore
from storage.backups import StateBackupStore
from storage.ownership import Actor
from storage.portability import PlatformPortabilityService
from storage.routes import route_priority_name, route_priority_value


ROUTING_AUTHORITIES = {"yaml", "database"}


class ConfigurationBridgeService:
    """Inventory, preview, and safely activate mounted YAML routing."""

    def __init__(
        self,
        config_service,
        portability: PlatformPortabilityService,
        backups: StateBackupStore,
        *,
        audit: AuditEventStore | None = None,
    ):
        self.config_service = config_service
        self.portability = portability
        self.backups = backups
        self.audit = audit
        self._lock = threading.RLock()

    def inventory(self, actor: Actor) -> dict:
        self._require_admin(actor)
        source = self.config_service.source_text()
        source_valid = True
        try:
            data = self._decode(source)
        except ValueError:
            source_valid = False
            snapshot = getattr(self.config_service.configuration, "snapshot", None)
            if callable(snapshot):
                data = snapshot()
            else:
                data = deepcopy(getattr(self.config_service.configuration, "data", {}))
        authority = self._authority(data)
        outputs = self._outputs(data, authority)
        routes = self._routes(data, authority)
        inputs = self._inputs(data)
        sections = [
            {
                "name": str(name),
                "management": "yaml",
                "active": self._section_active(str(name), value),
            }
            for name, value in data.items()
            if name not in {"outputs", "routing"}
        ]
        fingerprint = hashlib.sha256(source.encode("utf-8")).hexdigest()
        migratable_outputs = sum(
            1 for item in outputs if item["migratable"] and item["credential_configured"]
        )
        migratable_routes = sum(1 for item in routes if item["migratable"])
        return {
            "authority": authority,
            "source_valid": source_valid,
            "fingerprint": fingerprint,
            "inputs": inputs,
            "outputs": outputs,
            "routes": routes,
            "sections": sections,
            "migration_available": bool(
                authority == "yaml" and migratable_outputs and migratable_routes
            ),
            "summary": {
                "inputs": len(inputs),
                "outputs": len(outputs),
                "routes": len(routes),
                "migratable_outputs": migratable_outputs,
                "migratable_routes": migratable_routes,
            },
        }

    def preview(self, actor: Actor):
        self._require_admin(actor)
        inventory = self.inventory(actor)
        plan = self.portability.preview_v1_yaml(
            actor,
            self.config_service.source_text(),
        )
        warnings = list(plan.warnings)
        if inventory["authority"] == "database":
            warnings.append(
                "database routing is already authoritative; the YAML routes are rollback fallback"
            )
        return plan, inventory, tuple(warnings)

    def activate(
        self,
        actor: Actor,
        fingerprint: str,
    ) -> dict:
        self._require_admin(actor)
        with self._lock:
            source = self.config_service.source_text()
            data = self._decode(source)
            if self._authority(data) != "yaml":
                raise ValueError("database routing is already authoritative")
            plan = self.portability.preview_v1_yaml(actor, source)
            if not plan.valid:
                raise ValueError("migration preview contains errors")
            if not plan.destinations or not plan.routes:
                raise ValueError("mounted configuration has no migratable routes")
            if not hmac.compare_digest(plan.fingerprint, str(fingerprint or "")):
                raise ValueError("migration fingerprint does not match the preview")

            state_backup = self.backups.create(actor)
            application = None
            try:
                application = self.portability.apply_v1_yaml_with_resources(
                    actor,
                    source,
                    plan.fingerprint,
                )
                candidate = deepcopy(data)
                platform = candidate.setdefault("platform", {})
                if not isinstance(platform, dict):
                    raise ValueError("platform must be an object")
                platform["routing_authority"] = "database"
                config_backup = self.config_service.replace(candidate)
            except Exception:
                if application is not None:
                    self.portability.rollback_resources(actor, application["resources"])
                self._audit(actor, "configuration.migration", "failed")
                raise

            result = {
                **application["public"],
                "authority": "database",
                "configuration_backup": config_backup.name,
                "state_backup": state_backup.id,
            }
            self._audit(actor, "configuration.migration", "success", {
                "destinations": result["destinations_created"],
                "routes": result["routes_created"],
                "configuration_backup": result["configuration_backup"],
                "state_backup": result["state_backup"],
            })
            return result

    def set_authority(
        self,
        actor: Actor,
        authority: str,
        confirmation: str,
    ) -> dict:
        self._require_admin(actor)
        normalized = str(authority or "").strip().casefold()
        if normalized not in ROUTING_AUTHORITIES:
            raise ValueError("routing authority must be yaml or database")
        expected = f"USE {normalized.upper()} ROUTING"
        if str(confirmation or "") != expected:
            raise ValueError("routing authority confirmation is invalid")
        with self._lock:
            data = self.config_service.snapshot()
            previous = self._authority(data)
            if normalized == "database" and not self._platform_routes_exist():
                raise ValueError("database routing has no configured routes")
            platform = data.setdefault("platform", {})
            if not isinstance(platform, dict):
                raise ValueError("platform must be an object")
            platform["routing_authority"] = normalized
            backup = self.config_service.replace(data)
        self._audit(actor, "configuration.routing_authority", "success", {
            "previous": previous,
            "authority": normalized,
            "configuration_backup": backup.name,
        })
        return {
            "previous": previous,
            "authority": normalized,
            "configuration_backup": backup.name,
        }

    def _platform_routes_exist(self) -> bool:
        with self.portability.database.connect() as connection:
            return bool(connection.execute("SELECT 1 FROM routes LIMIT 1").fetchone())

    @staticmethod
    def _decode(source: str) -> dict:
        try:
            value = yaml.safe_load(str(source or "")) or {}
        except yaml.YAMLError as error:
            raise ValueError("mounted YAML configuration is invalid") from error
        if not isinstance(value, dict):
            raise ValueError("mounted YAML configuration root must be an object")
        return value

    @staticmethod
    def _authority(data: dict) -> str:
        platform = data.get("platform") or {}
        value = (
            platform.get("routing_authority", "yaml")
            if isinstance(platform, dict)
            else "yaml"
        )
        normalized = str(value or "yaml").strip().casefold()
        return normalized if normalized in ROUTING_AUTHORITIES else "yaml"

    @staticmethod
    def _section_active(name: str, value) -> bool:
        if isinstance(value, dict) and value.get("enabled") is False:
            return False
        return name not in {"api", "platform", "webui"} or not (
            isinstance(value, dict) and value.get("enabled") is False
        )

    @classmethod
    def _inputs(cls, data: dict) -> list[dict]:
        """Return the three operator-facing inputs with normalized names.

        Home Assistant, UniFi, and other integration endpoints are HTTP
        integrations, not separate listeners. Redfish is a logical input over
        the HTTP listener and can be disabled independently through its own
        lightweight YAML switch.
        """

        labels = {
            "smtp": "SMTP",
            "http": "HTTP",
            "redfish": "Redfish",
        }
        http_value = data.get("http")
        http_enabled = cls._section_active("http", http_value)
        inputs = []
        for name, label in labels.items():
            value = data.get(name)
            details = {}
            configured = name in data
            if name in {"smtp", "http"} and isinstance(value, dict):
                for key in ("host", "port", "max_body_bytes"):
                    if key in value:
                        details[key] = value[key]
            if name == "redfish":
                # The database-authoritative configuration intentionally removes
                # the legacy Redfish behavior block. In that normal state the
                # logical Redfish input follows HTTP until an explicit enabled
                # override is created from the Inputs page.
                configured = True
                redfish_enabled = cls._section_active(name, value)
                enabled = http_enabled and redfish_enabled
                details = {"transport": "HTTP"}
            else:
                enabled = configured and cls._section_active(name, value)
            inputs.append({
                "name": name,
                "label": label,
                "management": "yaml",
                "configured": configured,
                "enabled": enabled,
                "details": details,
            })
        return inputs

    @staticmethod
    def _outputs(data: dict, authority: str) -> list[dict]:
        outputs = data.get("outputs") or {}
        if not isinstance(outputs, dict):
            return []
        result = []
        for output_type, group in outputs.items():
            if not isinstance(group, dict):
                continue
            enabled = group.get("enabled", True) is True
            for target, settings in group.items():
                if target == "enabled" or not isinstance(settings, dict):
                    continue
                credential = settings.get("secret")
                if credential is None:
                    credential = settings.get("webhook")
                configured = bool(
                    credential not in (None, "", {})
                    and "PASTE_" not in str(credential).upper()
                )
                result.append({
                    "id": f"yaml:{output_type}:{target}",
                    "name": str(settings.get("name") or target),
                    "output_type": str(output_type),
                    "target": str(target),
                    "enabled": enabled and settings.get("enabled", True) is True,
                    "credential_configured": configured,
                    "management": "yaml",
                    "authority": authority == "yaml",
                    "migratable": str(output_type) in {"discord", "teams"},
                })
        return result

    @staticmethod
    def _routes(data: dict, authority: str) -> list[dict]:
        routing = data.get("routing") or {}
        if not isinstance(routing, dict):
            return []
        result = []
        for source, value in routing.items():
            if not isinstance(value, dict):
                continue
            entries = value.get("outputs")
            if entries is None:
                entries = [value]
            if not isinstance(entries, list):
                continue
            for position, entry in enumerate(entries, start=1):
                if not isinstance(entry, dict):
                    continue
                output_type = str(entry.get("output") or "")
                target = str(entry.get("target", "default"))
                match = entry.get("match") if isinstance(entry.get("match"), dict) else {}
                result.append({
                    "id": str(entry.get("id") or f"yaml:{source}:{position}"),
                    "name": str(entry.get("name") or f"{source} to {output_type} {target}"),
                    "source": str(source),
                    "output_type": output_type,
                    "target": target,
                    "filters": deepcopy(match),
                    "enabled": entry.get("enabled", True) is True,
                    "priority": route_priority_value(
                        entry.get("priority", 100 + position)
                    ),
                    "priority_name": route_priority_name(
                        entry.get("priority", 100 + position)
                    ),
                    "management": "yaml",
                    "authority": authority == "yaml",
                    "migratable": output_type in {"discord", "teams"},
                })
        return result

    @staticmethod
    def _require_admin(actor: Actor) -> None:
        if not actor.is_admin:
            raise PermissionError("administrator role is required")

    def _audit(self, actor, action, outcome, details=None):
        if self.audit is not None:
            self.audit.write(
                actor,
                action,
                "configuration",
                None,
                outcome,
                details,
            )
