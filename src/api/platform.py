"""Authenticated, owner-scoped HTTP contract for the Notifinho v2 platform."""

from __future__ import annotations

import json
import re
import uuid

from http.cookies import SimpleCookie

from api.response import APIResponse
from api.security import Principal, RateLimiter
from outputs.platform import PlatformOutputRegistry
from outputs.service import PlatformOutputService
from outputs.settings import normalize_output_settings
from storage.api_tokens import APITokenStore
from storage.audit_events import AuditEventStore
from storage.backups import StateBackupStore
from storage.bootstrap import BootstrapStore
from storage.configuration_bridge import ConfigurationBridgeService
from storage.configuration_sync import UnifiedConfigurationService
from storage.delivery import DeliveryHistoryStore, PlatformDeliveryService
from storage.destinations import DestinationStore
from storage.ownership import Actor
from storage.portability import PlatformPortabilityService
from storage.routes import RouteStore
from storage.sanitize import sanitize_text
from storage.secrets import SecretStore
from storage.sessions import SessionStore
from storage.users import UserStore


_RESOURCE_ID = re.compile(r"^[0-9a-f]{32}$")
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class PlatformAPI:
    """Expose platform state without mixing session and application authority."""

    def __init__(
        self,
        database,
        dispatcher,
        configuration,
        *,
        registry=None,
        config_service=None,
    ):
        self.database = database
        self.dispatcher = dispatcher
        self.configuration = configuration
        self.audit = AuditEventStore(database)
        self.users = UserStore(database)
        self.bootstrap = BootstrapStore(database, users=self.users)
        self.sessions = SessionStore(database)
        self.tokens = APITokenStore(database, audit=self.audit)
        self.secrets = SecretStore(database)
        self.portability = PlatformPortabilityService(
            database,
            secrets=self.secrets,
            audit=self.audit,
        )
        self.backups = StateBackupStore(
            database,
            audit=self.audit,
            retention=configuration.get(
                "platform",
                "backup_retention",
                default=20,
            ),
        )
        self.destinations = DestinationStore(database, audit=self.audit)
        self.routes = RouteStore(database, audit=self.audit)
        self.history = DeliveryHistoryStore(database)
        self.registry = registry or PlatformOutputRegistry()
        self.outputs = PlatformOutputService(
            self.destinations,
            self.secrets,
            self.registry,
            audit=self.audit,
        )
        self.delivery = PlatformDeliveryService(
            self.routes,
            self.destinations,
            self.secrets,
            self.history,
            self.registry.delivery_adapters(),
        )
        self.configuration_bridge = (
            ConfigurationBridgeService(
                config_service,
                self.portability,
                self.backups,
                audit=self.audit,
            )
            if config_service is not None
            else None
        )
        self.configuration_sync = (
            UnifiedConfigurationService(
                config_service,
                database,
                audit=self.audit,
            )
            if config_service is not None
            and getattr(config_service, "reloadable", True)
            else None
        )
        self.token_limiter = RateLimiter()
        self.login_limiter = RateLimiter()
        self.bootstrap_limiter = RateLimiter()
        self.session_limiter = RateLimiter()

    @property
    def secure_cookies(self) -> bool:
        return self.configuration.get(
            "platform",
            "secure_cookies",
            default=True,
        ) is not False

    def handle(self, method, path, payload, headers, client) -> APIResponse:
        method = str(method or "").upper()
        try:
            if path == "/api/v2/bootstrap":
                return self._bootstrap(method, payload, client)
            if path == "/api/v2/session" and method == "POST":
                return self._login(payload, client)
            if path == "/api/v2/events" and method == "POST":
                return self._submit_event(payload, headers, client)
            principal = self._session(
                headers,
                require_csrf=method not in _SAFE_METHODS,
            )
        except Exception:
            return APIResponse(500, {"error": "request failed"})
        if principal is None:
            return APIResponse(401, {"error": "authentication required"})
        session_rate = Principal(
            name=f"platform-session:{principal.session_id}",
            role=principal.role,
            sources=frozenset(),
            rate_limit_per_minute=240,
        )
        if not self.session_limiter.allow(session_rate, str(client)):
            return APIResponse(429, {"error": "rate limit exceeded"})
        actor = principal.actor

        try:
            if path == "/api/v2/session":
                return self._session_endpoint(method, principal)
            if path == "/api/v2/users":
                return self._users_endpoint(method, payload, actor)
            if path == "/api/v2/account/password":
                return self._own_password(method, payload, principal)
            if path == "/api/v2/preferences":
                return self._preferences_endpoint(method, payload, actor)
            if path == "/api/v2/tokens":
                return self._tokens_endpoint(method, payload, actor)
            if path == "/api/v2/destinations":
                return self._destinations_endpoint(method, payload, actor)
            if path == "/api/v2/routes":
                return self._routes_endpoint(method, payload, actor)
            if path == "/api/v2/deliveries":
                return self._deliveries_endpoint(method, actor)
            if path == "/api/v2/audit-events":
                return self._audit_endpoint(method, actor)
            if path == "/api/v2/portability/export":
                return self._portability_export(method, actor)
            if path == "/api/v2/portability/preview":
                return self._portability_preview(method, payload, actor)
            if path == "/api/v2/portability/import":
                return self._portability_import(method, payload, actor)
            if path == "/api/v2/migrations/v1/preview":
                return self._v1_migration_preview(method, payload, actor)
            if path == "/api/v2/migrations/v1/import":
                return self._v1_migration_import(method, payload, actor)
            if path == "/api/v2/configuration/inventory":
                return self._configuration_inventory(method, actor)
            if path == "/api/v2/configuration/migration/preview":
                return self._configuration_migration_preview(method, actor)
            if path == "/api/v2/configuration/migration/apply":
                return self._configuration_migration_apply(method, payload, actor)
            if path == "/api/v2/configuration/routing-authority":
                return self._configuration_authority(method, payload, actor)
            if path == "/api/v2/backups":
                return self._backups_endpoint(method, actor)
            response = self._resource_endpoint(method, path, payload, actor)
            if response is not None:
                return response
            return APIResponse(404, {"error": "resource not found"})
        except KeyError:
            return APIResponse(404, {"error": "resource not found"})
        except PermissionError:
            return APIResponse(403, {"error": "operation is not permitted"})
        except (TypeError, ValueError):
            return APIResponse(400, {"error": "request is invalid"})
        except Exception:
            return APIResponse(500, {"error": "request failed"})

    def _login(self, payload, client) -> APIResponse:
        limiter_principal = Principal(
            name="platform-login",
            role="application",
            sources=frozenset(),
            rate_limit_per_minute=10,
        )
        if not self.login_limiter.allow(limiter_principal, str(client)):
            return APIResponse(429, {"error": "rate limit exceeded"})
        if not isinstance(payload, dict) or set(payload) - {"username", "password"}:
            return APIResponse(400, {"error": "request is invalid"})
        user = self.users.authenticate(
            str(payload.get("username") or ""),
            str(payload.get("password") or ""),
        )
        if user is None:
            self.audit.write(None, "session.login", "session", None, "denied")
            return APIResponse(401, {"error": "invalid credentials"})
        credentials = self.sessions.create(user.id)
        self.audit.write(
            user.actor,
            "session.login",
            "session",
            credentials.session_id,
            "success",
        )
        return self._session_response(user, credentials)

    def _bootstrap(self, method, payload, client) -> APIResponse:
        status = self.bootstrap.status()
        if method == "GET":
            return APIResponse(
                200,
                {
                    "required": status.required,
                    "expires_at": status.expires_at,
                },
                (("Cache-Control", "no-store"),),
            )
        if method != "POST":
            return self._method_not_allowed("GET, POST")
        if not status.required:
            return APIResponse(409, {"error": "platform setup is already complete"})
        limiter_principal = Principal(
            name="platform-bootstrap",
            role="application",
            sources=frozenset(),
            rate_limit_per_minute=5,
        )
        if not self.bootstrap_limiter.allow(limiter_principal, str(client)):
            return APIResponse(429, {"error": "rate limit exceeded"})
        if not isinstance(payload, dict) or set(payload) != {
            "token",
            "username",
            "password",
        }:
            return APIResponse(400, {"error": "request is invalid"})
        try:
            user = self.bootstrap.consume(
                str(payload.get("token") or ""),
                str(payload.get("username") or ""),
                str(payload.get("password") or ""),
            )
        except PermissionError:
            self.audit.write(None, "platform.bootstrap", "user", None, "denied")
            return APIResponse(401, {"error": "setup token is invalid or expired"})
        except ValueError:
            return APIResponse(400, {"error": "setup account details are invalid"})
        self.audit.write(
            user.actor,
            "platform.bootstrap",
            "user",
            user.id,
            "success",
        )
        return self._session_response(user)

    def _session_response(self, user, credentials=None) -> APIResponse:
        credentials = credentials or self.sessions.create(user.id)
        headers = (
            ("Set-Cookie", credentials.cookie(secure=self.secure_cookies)),
            ("Set-Cookie", self._csrf_cookie(credentials.csrf_token)),
            ("Cache-Control", "no-store"),
        )
        return APIResponse(
            200,
            {
                "user": self._user(user),
                "csrf_token": credentials.csrf_token,
                "expires_at": credentials.expires_at,
            },
            headers,
        )

    def _session_endpoint(self, method, principal) -> APIResponse:
        if method == "GET":
            return APIResponse(
                200,
                {
                    "user": self._user(self.users.get(principal.user_id)),
                    "expires_at": principal.expires_at,
                    "csrf_required": True,
                },
                (("Cache-Control", "no-store"),),
            )
        if method == "DELETE":
            self.sessions.revoke(principal.session_id)
            self.audit.write(
                principal.actor,
                "session.logout",
                "session",
                principal.session_id,
                "success",
            )
            return APIResponse(204, None, self._clear_cookies())
        return self._method_not_allowed("GET, DELETE")

    def _users_endpoint(self, method, payload, actor) -> APIResponse:
        self._require_admin(actor)
        if method == "GET":
            return APIResponse(200, {"users": [self._user(item) for item in self.users.list()]})
        if method == "POST":
            data = self._object(payload, {"username", "password", "role"})
            user = self.users.create(
                data.get("username"),
                data.get("password"),
                data.get("role", "user"),
            )
            self.audit.write(actor, "user.create", "user", user.id, "success")
            return APIResponse(201, {"user": self._user(user)})
        return self._method_not_allowed("GET, POST")

    def _own_password(self, method, payload, principal) -> APIResponse:
        if method != "PUT":
            return self._method_not_allowed("PUT")
        data = self._object(payload, {"current_password", "new_password"})
        user = self.users.authenticate(
            principal.username,
            str(data.get("current_password") or ""),
        )
        if user is None:
            return APIResponse(403, {"error": "operation is not permitted"})
        self.users.reset_password(user.id, data.get("new_password"))
        self.audit.write(user.actor, "user.password", "user", user.id, "success")
        return APIResponse(204, None, self._clear_cookies())

    def _tokens_endpoint(self, method, payload, actor) -> APIResponse:
        if method == "GET":
            owner_id = actor.user_id
            tokens = [
                {**self._token(item), "management": "platform", "enabled": item.revoked_at is None}
                for item in self.tokens.list_for_owner(actor, owner_id)
            ]
            if actor.is_admin and self.configuration_sync is not None:
                tokens.extend(self.configuration_sync.legacy_applications())
            return APIResponse(
                200,
                {"tokens": tokens},
            )
        if method == "POST":
            data = self._object(
                payload,
                {
                    "owner_user_id",
                    "name",
                    "source_scopes",
                    "role",
                    "rate_limit_per_minute",
                    "expires_at",
                },
            )
            owner_id = self._owner(data, actor)
            credentials = self.tokens.create(
                actor,
                owner_id,
                data.get("name"),
                source_scopes=data.get("source_scopes", []),
                role=data.get("role", "application"),
                rate_limit_per_minute=data.get("rate_limit_per_minute", 60),
                expires_at=data.get("expires_at"),
            )
            return APIResponse(
                201,
                {"token": self._token(credentials.token), "value": credentials.value},
                (("Cache-Control", "no-store"),),
            )
        return self._method_not_allowed("GET, POST")

    def _destinations_endpoint(self, method, payload, actor) -> APIResponse:
        if self.configuration_sync is not None:
            if method == "GET":
                return APIResponse(
                    200,
                    {
                        "destinations": [
                            {**self._destination(item), "management": "yaml"}
                            for item in self.configuration_sync.list_destinations(actor)
                        ]
                    },
                )
            self._require_admin(actor)
            if method == "POST":
                data = self._object(
                    payload,
                    {"name", "output_type", "settings", "shared", "enabled", "secret"},
                )
                destination = self.configuration_sync.create_destination(actor, data)
                return APIResponse(
                    201,
                    {"destination": {**self._destination(destination), "management": "yaml"}},
                )
            return self._method_not_allowed("GET, POST")
        if method == "GET":
            return APIResponse(
                200,
                {
                    "destinations": [
                        self._destination(item)
                        for item in self.destinations.list_visible(actor)
                    ]
                },
            )
        if method == "POST":
            data = self._object(
                payload,
                {
                    "owner_user_id",
                    "name",
                    "output_type",
                    "settings",
                    "shared",
                    "enabled",
                    "secret",
                },
            )
            owner_id = self._owner(data, actor)
            output_type = data.get("output_type")
            settings = data.get("settings", {})
            normalize_output_settings(output_type, settings)
            secret_value = (
                self._secret_value(data.get("secret"))
                if "secret" in data
                else None
            )
            destination = self.destinations.create(
                actor,
                owner_id,
                data.get("name"),
                output_type,
                settings=settings,
                shared=self._boolean(data, "shared", False),
                enabled=self._boolean(data, "enabled", True),
            )
            if secret_value is not None:
                try:
                    secret = self.secrets.create(
                        actor,
                        owner_id,
                        self._secret_name(destination.name),
                        f"{destination.output_type}-credentials",
                        secret_value,
                    )
                    destination = self.destinations.set_secret(
                        actor,
                        destination.id,
                        secret.id,
                    )
                except Exception:
                    self.destinations.delete(actor, destination.id)
                    raise
            return APIResponse(201, {"destination": self._destination(destination)})
        return self._method_not_allowed("GET, POST")

    def _routes_endpoint(self, method, payload, actor) -> APIResponse:
        if self.configuration_sync is not None:
            if method == "GET":
                return APIResponse(
                    200,
                    {
                        "routes": [
                            {**self._route(item), "management": "yaml"}
                            for item in self.configuration_sync.list_routes(actor)
                        ]
                    },
                )
            self._require_admin(actor)
            if method == "POST":
                data = self._object(
                    payload,
                    {
                        "name",
                        "source",
                        "destination_id",
                        "filters",
                        "priority",
                        "enabled",
                    },
                )
                route = self.configuration_sync.create_route(actor, data)
                return APIResponse(
                    201,
                    {"route": {**self._route(route), "management": "yaml"}},
                )
            return self._method_not_allowed("GET, POST")
        if method == "GET":
            routes = self.routes.list_for_owner(actor, actor.user_id)
            return APIResponse(200, {"routes": [self._route(item) for item in routes]})
        if method == "POST":
            data = self._object(
                payload,
                {
                    "owner_user_id",
                    "name",
                    "source",
                    "destination_id",
                    "filters",
                    "priority",
                    "enabled",
                },
            )
            route = self.routes.create(
                actor,
                self._owner(data, actor),
                data.get("name"),
                data.get("source"),
                data.get("destination_id"),
                filters=data.get("filters", {}),
                priority=data.get("priority", 100),
                enabled=self._boolean(data, "enabled", True),
            )
            return APIResponse(201, {"route": self._route(route)})
        return self._method_not_allowed("GET, POST")

    def _deliveries_endpoint(self, method, actor) -> APIResponse:
        if method != "GET":
            return self._method_not_allowed("GET")
        attempts = self.history.list_visible(actor, limit=100)
        return APIResponse(200, {"deliveries": [self._delivery(item) for item in attempts]})

    def _audit_endpoint(self, method, actor) -> APIResponse:
        if method != "GET":
            return self._method_not_allowed("GET")
        events = self.audit.list_visible(actor, limit=100)
        return APIResponse(200, {"audit_events": [self._audit(item) for item in events]})

    def _portability_export(self, method, actor) -> APIResponse:
        self._require_admin(actor)
        if method != "GET":
            return self._method_not_allowed("GET")
        return APIResponse(200, {"document": self.portability.export_document(actor)})

    def _portability_preview(self, method, payload, actor) -> APIResponse:
        self._require_admin(actor)
        if method != "POST":
            return self._method_not_allowed("POST")
        data = self._object(payload, {"document"})
        if "document" not in data:
            raise ValueError("document is required")
        plan = self.portability.preview_document(actor, data["document"])
        return APIResponse(200, {"preview": plan.public()})

    def _portability_import(self, method, payload, actor) -> APIResponse:
        self._require_admin(actor)
        if method != "POST":
            return self._method_not_allowed("POST")
        data = self._object(payload, {"document", "fingerprint", "confirm"})
        if self._boolean(data, "confirm") is not True:
            raise ValueError("confirmed import is required")
        result = self.portability.apply_document(
            actor,
            data.get("document"),
            str(data.get("fingerprint") or ""),
        )
        if self.configuration_sync is not None:
            result["yaml_resources_adopted"] = self.configuration_sync.adopt_unmanaged_resources(actor)
        return APIResponse(200, {"import": result})

    def _v1_migration_preview(self, method, payload, actor) -> APIResponse:
        self._require_admin(actor)
        if method != "POST":
            return self._method_not_allowed("POST")
        data = self._object(payload, {"yaml"})
        plan = self.portability.preview_v1_yaml(actor, data.get("yaml"))
        return APIResponse(200, {"preview": plan.public()})

    def _v1_migration_import(self, method, payload, actor) -> APIResponse:
        self._require_admin(actor)
        if method != "POST":
            return self._method_not_allowed("POST")
        data = self._object(payload, {"yaml", "fingerprint", "confirm"})
        if self._boolean(data, "confirm") is not True:
            raise ValueError("confirmed import is required")
        result = self.portability.apply_v1_yaml(
            actor,
            data.get("yaml"),
            str(data.get("fingerprint") or ""),
        )
        if self.configuration_sync is not None:
            result["yaml_resources_adopted"] = self.configuration_sync.adopt_unmanaged_resources(actor)
        return APIResponse(200, {"import": result})

    def _configuration_inventory(self, method, actor) -> APIResponse:
        self._require_admin(actor)
        if method != "GET":
            return self._method_not_allowed("GET")
        bridge = self._configuration_bridge()
        configuration = bridge.inventory(actor)
        if self.configuration_sync is not None:
            status = self.configuration_sync.synchronize()
            configuration["sync"] = {
                "ready": status.ready,
                "changed": status.changed,
                "errors": list(status.errors),
                "fingerprint": status.fingerprint,
            }
            configuration["applications"] = self.configuration_sync.legacy_applications()
            configuration["preferences"] = self.configuration_sync.preferences()
            configuration["authority"] = "yaml"
            configuration["migration_available"] = False
        return APIResponse(
            200,
            {"configuration": configuration},
            (("Cache-Control", "no-store"),),
        )

    def _preferences_endpoint(self, method, payload, actor) -> APIResponse:
        if self.configuration_sync is None:
            return APIResponse(404, {"error": "resource not found"})
        if method == "GET":
            return APIResponse(200, {"preferences": self.configuration_sync.preferences()})
        if method == "PUT":
            self._require_admin(actor)
            data = self._object(payload, {"timezone", "language", "time_format"})
            if set(data) != {"timezone", "language", "time_format"}:
                raise ValueError("every preference is required")
            return APIResponse(
                200,
                {"preferences": self.configuration_sync.update_preferences(actor, data)},
            )
        return self._method_not_allowed("GET, PUT")

    def _configuration_migration_preview(self, method, actor) -> APIResponse:
        self._require_admin(actor)
        if self.configuration_sync is not None:
            raise ValueError("routing-authority migration is retired by unified YAML configuration")
        if method != "POST":
            return self._method_not_allowed("POST")
        plan, inventory, warnings = self._configuration_bridge().preview(actor)
        public = plan.public()
        public["warnings"] = list(warnings)
        public["inventory"] = inventory["summary"]
        public["current_authority"] = inventory["authority"]
        return APIResponse(
            200,
            {"preview": public},
            (("Cache-Control", "no-store"),),
        )

    def _configuration_migration_apply(self, method, payload, actor) -> APIResponse:
        self._require_admin(actor)
        if self.configuration_sync is not None:
            raise ValueError("routing-authority migration is retired by unified YAML configuration")
        if method != "POST":
            return self._method_not_allowed("POST")
        data = self._object(payload, {"fingerprint", "confirm"})
        if self._boolean(data, "confirm") is not True:
            raise ValueError("confirmed migration is required")
        result = self._configuration_bridge().activate(
            actor,
            str(data.get("fingerprint") or ""),
        )
        return APIResponse(200, {"migration": result})

    def _configuration_authority(self, method, payload, actor) -> APIResponse:
        self._require_admin(actor)
        if self.configuration_sync is not None:
            raise ValueError("routing authority is fixed to unified YAML configuration")
        if method != "PUT":
            return self._method_not_allowed("PUT")
        data = self._object(payload, {"authority", "confirmation"})
        result = self._configuration_bridge().set_authority(
            actor,
            str(data.get("authority") or ""),
            str(data.get("confirmation") or ""),
        )
        return APIResponse(200, {"routing": result})

    def _configuration_bridge(self) -> ConfigurationBridgeService:
        if self.configuration_bridge is None:
            raise RuntimeError("mounted configuration bridge is unavailable")
        return self.configuration_bridge

    def _backups_endpoint(self, method, actor) -> APIResponse:
        self._require_admin(actor)
        if method == "GET":
            return APIResponse(
                200,
                {"backups": [item.public() for item in self.backups.list(actor)]},
            )
        if method == "POST":
            backup = self.backups.create(actor)
            return APIResponse(201, {"backup": backup.public()})
        return self._method_not_allowed("GET, POST")

    def _resource_endpoint(self, method, path, payload, actor):
        backup_match = re.fullmatch(
            r"/api/v2/backups/(state-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8})/restore",
            path,
        )
        if backup_match:
            return self._backup_restore(
                method,
                payload,
                actor,
                backup_match.group(1),
            )

        user_match = re.fullmatch(
            r"/api/v2/users/([0-9a-f]{32})(?:/(password|tokens|routes))?",
            path,
        )
        if user_match:
            return self._user_resource(method, payload, actor, *user_match.groups())

        token_match = re.fullmatch(r"/api/v2/tokens/([0-9a-f]{32})/(rotate|revoke)", path)
        if token_match:
            return self._token_resource(method, actor, *token_match.groups())

        destination_match = re.fullmatch(
            r"/api/v2/destinations/([0-9a-f]{32})(?:/(preview|test))?",
            path,
        )
        if destination_match:
            return self._destination_resource(
                method,
                payload,
                actor,
                *destination_match.groups(),
            )

        route_match = re.fullmatch(r"/api/v2/routes/([0-9a-f]{32})", path)
        if route_match:
            return self._route_resource(method, payload, actor, route_match.group(1))
        return None

    def _backup_restore(self, method, payload, actor, backup_id):
        self._require_admin(actor)
        if method != "POST":
            return self._method_not_allowed("POST")
        data = self._object(payload, {"confirmation"})
        result = self.backups.restore(
            actor,
            backup_id,
            str(data.get("confirmation") or ""),
        )
        return APIResponse(200, {"restore": result}, self._clear_cookies())

    def _user_resource(self, method, payload, actor, user_id, action):
        self._require_admin(actor)
        if action == "tokens":
            if method != "GET":
                return self._method_not_allowed("GET")
            tokens = self.tokens.list_for_owner(actor, user_id)
            return APIResponse(200, {"tokens": [self._token(item) for item in tokens]})
        if action == "routes":
            if method != "GET":
                return self._method_not_allowed("GET")
            routes = self.routes.list_for_owner(actor, user_id)
            return APIResponse(200, {"routes": [self._route(item) for item in routes]})
        if action == "password":
            if method != "PUT":
                return self._method_not_allowed("PUT")
            if user_id == actor.user_id:
                raise PermissionError(
                    "the current account must change its password from Account security"
                )
            data = self._object(payload, {"password"})
            user = self.users.reset_password(user_id, data.get("password"))
            self.audit.write(actor, "user.password", "user", user.id, "success")
            return APIResponse(200, {"user": self._user(user)})
        if method == "GET":
            return APIResponse(200, {"user": self._user(self.users.get(user_id))})
        if method == "PATCH":
            data = self._object(payload, {"enabled"})
            if "enabled" not in data:
                raise ValueError("enabled is required")
            user = self.users.set_enabled(user_id, self._boolean(data, "enabled"))
            self.audit.write(
                actor,
                "user.enable" if user.enabled else "user.disable",
                "user",
                user.id,
                "success",
            )
            return APIResponse(200, {"user": self._user(user)})
        return self._method_not_allowed("GET, PATCH")

    def _token_resource(self, method, actor, token_id, action):
        if method != "POST":
            return self._method_not_allowed("POST")
        if action == "rotate":
            credentials = self.tokens.rotate(actor, token_id)
            return APIResponse(
                200,
                {"token": self._token(credentials.token), "value": credentials.value},
                (("Cache-Control", "no-store"),),
            )
        token = self.tokens.revoke(actor, token_id)
        return APIResponse(200, {"token": self._token(token)})

    def _destination_resource(self, method, payload, actor, destination_id, action):
        if action in {"preview", "test"}:
            if method != "POST":
                return self._method_not_allowed("POST")
            if action == "test" and self.configuration_sync is not None:
                self._require_admin(actor)
            data = self._object(payload, {"event"})
            notification = self._notification(data.get("event"))
            if action == "preview":
                preview = self.outputs.preview(actor, destination_id, notification)
                return APIResponse(
                    200,
                    {
                        "preview": {
                            "output_type": preview.output_type,
                            "content_type": preview.content_type,
                            "payload": preview.payload,
                            "metadata": preview.metadata,
                        }
                    },
                )
            result = self.outputs.test_delivery(actor, destination_id, notification)
            return APIResponse(200, {"result": self._delivery_result(result)})

        if method == "GET":
            if self.configuration_sync is not None:
                item = next(
                    (
                        value
                        for value in self.configuration_sync.list_destinations(actor)
                        if value.id == destination_id
                    ),
                    None,
                )
                if item is None:
                    raise KeyError("destination not found")
                return APIResponse(200, {"destination": {**self._destination(item), "management": "yaml"}})
            destination = self.destinations.get(actor, destination_id)
            return APIResponse(200, {"destination": self._destination(destination)})
        if method == "PATCH":
            data = self._object(payload, {"name", "settings", "enabled", "shared", "secret"})
            if self.configuration_sync is not None:
                destination = self.configuration_sync.update_destination(actor, destination_id, data)
                return APIResponse(
                    200,
                    {"destination": {**self._destination(destination), "management": "yaml"}},
                )
            destination = self.destinations.get(actor, destination_id)
            if destination.owner_user_id != actor.user_id and not actor.is_admin:
                raise PermissionError("destination cannot be changed by this user")
            if "shared" in data and not actor.is_admin:
                raise PermissionError("only administrators can change sharing")
            if "settings" in data:
                normalize_output_settings(destination.output_type, data.get("settings"))
            if "enabled" in data:
                self._boolean(data, "enabled")
            if "shared" in data:
                self._boolean(data, "shared")
            secret_value = (
                self._secret_value(data.get("secret"))
                if "secret" in data
                else None
            )
            if "settings" in data:
                destination = self.destinations.update_settings(
                    actor,
                    destination_id,
                    data.get("settings"),
                )
            if "enabled" in data:
                destination = self.destinations.set_enabled(
                    actor,
                    destination_id,
                    self._boolean(data, "enabled"),
                )
            if "shared" in data:
                destination = self.destinations.set_shared(
                    actor,
                    destination_id,
                    self._boolean(data, "shared"),
                )
            if secret_value is not None:
                target = self.destinations.for_delivery_metadata(actor, destination_id)
                if target.secret_id:
                    self.secrets.rotate(
                        actor,
                        target.secret_id,
                        secret_value,
                    )
                else:
                    secret = self.secrets.create(
                        actor,
                        target.destination.owner_user_id,
                        self._secret_name(target.destination.name),
                        f"{target.destination.output_type}-credentials",
                        secret_value,
                    )
                    destination = self.destinations.set_secret(
                        actor,
                        destination_id,
                        secret.id,
                    )
            return APIResponse(200, {"destination": self._destination(destination)})
        if method == "DELETE":
            if self.configuration_sync is not None:
                self.configuration_sync.delete_destination(actor, destination_id)
                return APIResponse(204)
            self.destinations.delete(actor, destination_id)
            return APIResponse(204)
        return self._method_not_allowed("GET, PATCH, DELETE")

    def _route_resource(self, method, payload, actor, route_id):
        if method == "GET":
            if self.configuration_sync is not None:
                item = next(
                    (
                        value
                        for value in self.configuration_sync.list_routes(actor)
                        if value.id == route_id
                    ),
                    None,
                )
                if item is None:
                    raise KeyError("route not found")
                return APIResponse(200, {"route": {**self._route(item), "management": "yaml"}})
            return APIResponse(200, {"route": self._route(self.routes.get(actor, route_id))})
        if method == "PATCH":
            data = self._object(
                payload,
                {"name", "source", "destination_id", "filters", "priority", "enabled"},
            )
            if any(value is None for value in data.values()):
                raise ValueError("route fields cannot be null")
            if self.configuration_sync is not None:
                route = self.configuration_sync.update_route(actor, route_id, data)
                return APIResponse(200, {"route": {**self._route(route), "management": "yaml"}})
            route = self.routes.update(actor, route_id, **data)
            return APIResponse(200, {"route": self._route(route)})
        if method == "DELETE":
            if self.configuration_sync is not None:
                self.configuration_sync.delete_route(actor, route_id)
                return APIResponse(204)
            self.routes.delete(actor, route_id)
            return APIResponse(204)
        return self._method_not_allowed("GET, PATCH, DELETE")

    def _submit_event(self, payload, headers, client) -> APIResponse:
        try:
            notification = self._notification(payload)
        except (TypeError, ValueError):
            return APIResponse(400, {"error": "request is invalid"})
        token_value = self._bearer(headers)
        token_principal = self.tokens.authenticate(token_value, notification.source)
        actor = token_principal.actor if token_principal else None
        if token_principal is not None:
            if not self.token_limiter.allow(token_principal, str(client)):
                return APIResponse(429, {"error": "rate limit exceeded"})
        else:
            session = self._session(headers, require_csrf=True)
            actor = session.actor if session else None
            if session is not None:
                session_rate = Principal(
                    name=f"platform-session:{session.session_id}",
                    role=session.role,
                    sources=frozenset(),
                    rate_limit_per_minute=240,
                )
                if not self.session_limiter.allow(session_rate, str(client)):
                    return APIResponse(429, {"error": "rate limit exceeded"})
        if actor is None:
            return APIResponse(401, {"error": "authentication required"})
        try:
            summary = self.delivery.deliver(actor, notification)
            self.audit.write(
                actor,
                "event.submit",
                "event",
                None,
                "success",
                {"source": notification.source, "matched": summary.matched_routes},
            )
        except Exception:
            return APIResponse(500, {"error": "request failed"})
        return APIResponse(
            202,
            {
                "accepted": True,
                "matched": summary.matched_routes,
                "delivered": summary.delivered,
                "failed": summary.failed,
                "attempts": summary.attempts,
            },
        )

    def _session(self, headers, *, require_csrf):
        token = self._session_token(headers)
        csrf = self._header(headers, "X-CSRF-Token")
        return self.sessions.authenticate(
            token,
            csrf_token=csrf,
            require_csrf=require_csrf,
        )

    def _session_token(self, headers) -> str:
        raw = self._header(headers, "Cookie")
        if not raw:
            return ""
        try:
            parsed = SimpleCookie()
            parsed.load(raw)
        except Exception:
            return ""
        for name in ("__Host-notifinho_session", "notifinho_session"):
            if name in parsed:
                return str(parsed[name].value)
        return ""

    @staticmethod
    def _header(headers, name) -> str:
        if hasattr(headers, "get"):
            direct = headers.get(name)
            if direct is not None:
                return str(direct)
        wanted = str(name).casefold()
        for key, value in (headers or {}).items():
            if str(key).casefold() == wanted:
                return str(value)
        return ""

    def _bearer(self, headers) -> str:
        authorization = self._header(headers, "Authorization")
        if authorization.casefold().startswith("bearer "):
            return authorization[7:].strip()
        return self._header(headers, "X-Notifinho-Token")

    def _notification(self, value):
        if not isinstance(value, dict):
            raise ValueError("event is required")
        parsed = self.dispatcher.parse_webhook("event_api", value)
        if parsed is None:
            raise ValueError("event is invalid")
        return parsed

    def _csrf_cookie(self, token) -> str:
        name = "__Host-notifinho_csrf" if self.secure_cookies else "notifinho_csrf"
        attributes = [
            f"{name}={token}",
            "Path=/",
            "SameSite=Strict",
        ]
        if self.secure_cookies:
            attributes.append("Secure")
        return "; ".join(attributes)

    def _clear_cookies(self):
        session_name = (
            "__Host-notifinho_session" if self.secure_cookies else "notifinho_session"
        )
        csrf_name = "__Host-notifinho_csrf" if self.secure_cookies else "notifinho_csrf"
        secure = "; Secure" if self.secure_cookies else ""
        return (
            (
                "Set-Cookie",
                f"{session_name}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0{secure}",
            ),
            (
                "Set-Cookie",
                f"{csrf_name}=; Path=/; SameSite=Strict; Max-Age=0{secure}",
            ),
            ("Cache-Control", "no-store"),
        )

    @staticmethod
    def _object(value, allowed):
        if not isinstance(value, dict) or set(value) - set(allowed):
            raise ValueError("request contains unsupported fields")
        return dict(value)

    @staticmethod
    def _boolean(data, key, default=None):
        if key not in data:
            return default
        value = data[key]
        if not isinstance(value, bool):
            raise ValueError(f"{key} must be a boolean")
        return value

    @staticmethod
    def _owner(data, actor):
        owner_id = str(data.get("owner_user_id") or actor.user_id)
        if owner_id != actor.user_id and not actor.is_admin:
            raise PermissionError("owner cannot be changed")
        if not _RESOURCE_ID.fullmatch(owner_id):
            raise ValueError("owner_user_id is invalid")
        return owner_id

    @staticmethod
    def _require_admin(actor):
        if not actor.is_admin:
            raise PermissionError("administrator access is required")

    @staticmethod
    def _secret_value(value):
        if isinstance(value, str):
            text = value
        elif isinstance(value, dict):
            text = json.dumps(value, sort_keys=True, separators=(",", ":"))
        else:
            raise ValueError("secret must be a string or object")
        if not text or len(text.encode("utf-8")) > 64 * 1024:
            raise ValueError("secret is empty or too large")
        return text

    @staticmethod
    def _secret_name(destination_name):
        return f"{str(destination_name or 'destination')[:80]} {uuid.uuid4().hex[:12]}"

    @staticmethod
    def _method_not_allowed(allow):
        return APIResponse(405, None, (("Allow", allow),))

    @staticmethod
    def _user(item):
        return {
            "id": item.id,
            "username": item.username,
            "role": item.role,
            "enabled": item.enabled,
            "locked_until": item.locked_until,
            "last_login_at": item.last_login_at,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    @staticmethod
    def _token(item):
        return {
            "id": item.id,
            "owner_user_id": item.owner_user_id,
            "name": item.name,
            "role": item.role,
            "source_scopes": list(item.source_scopes),
            "rate_limit_per_minute": item.rate_limit_per_minute,
            "version": item.version,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
            "expires_at": item.expires_at,
            "last_used_at": item.last_used_at,
            "revoked_at": item.revoked_at,
        }

    @staticmethod
    def _destination(item):
        return {
            "id": item.id,
            "owner_user_id": item.owner_user_id,
            "name": item.name,
            "output_type": item.output_type,
            "settings": item.settings,
            "shared": item.shared,
            "enabled": item.enabled,
            "secret_configured": item.secret_configured,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    @staticmethod
    def _route(item):
        return {
            "id": item.id,
            "owner_user_id": item.owner_user_id,
            "destination_id": item.destination_id,
            "name": item.name,
            "source": item.source,
            "filters": {key: list(values) for key, values in item.filters.items()},
            "priority": item.priority,
            "enabled": item.enabled,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    @staticmethod
    def _delivery(item):
        return {
            "id": item.id,
            "delivery_id": item.delivery_id,
            "owner_user_id": item.owner_user_id,
            "route_id": item.route_id,
            "destination_id": item.destination_id,
            "source": item.source,
            "title": item.title,
            "severity": item.severity,
            "outcome": item.outcome,
            "attempt_number": item.attempt_number,
            "retryable": item.retryable,
            "response_status": item.response_status,
            "error_code": item.error_code,
            "safe_error": item.safe_error,
            "created_at": item.created_at,
            "completed_at": item.completed_at,
        }

    @staticmethod
    def _delivery_result(item):
        return {
            "success": item.success,
            "retryable": item.retryable,
            "response_status": item.response_status,
            "error_code": item.error_code,
            "safe_error": sanitize_text(item.safe_error)[:500],
        }

    @staticmethod
    def _audit(item):
        return {
            "id": item.id,
            "actor_user_id": item.actor_user_id,
            "action": item.action,
            "resource_type": item.resource_type,
            "resource_id": item.resource_id,
            "outcome": item.outcome,
            "details": item.details,
            "created_at": item.created_at,
        }
