"""Backend API endpoints layered on the existing notification pipeline."""

from __future__ import annotations

import time

from pathlib import Path

from api.audit import AuditLog
from api.config_service import ConfigService
from api.platform import PlatformAPI
from api.response import APIResponse
from api.security import RateLimiter, TokenAuthenticator
from formatters.presentation import PresentationMixin
from outputs.discord import DiscordOutput
from outputs.teams import TeamsOutput
from version import VERSION


class APIService:
    def __init__(
        self,
        dispatcher,
        router,
        configuration,
        *,
        platform_database=None,
        platform_registry=None,
    ):
        self.dispatcher = dispatcher
        self.router = router
        self.configuration = configuration
        root = Path(__file__).resolve().parents[2]
        self.config_service = ConfigService(root / "config" / "config.yaml", configuration)
        self.audit = AuditLog(root / "logs" / "audit.log")
        self.authenticator = TokenAuthenticator(configuration)
        self.rate_limiter = RateLimiter()
        self.started = time.monotonic()
        self.sanitizer = PresentationMixin()
        self.platform = (
            PlatformAPI(
                platform_database,
                dispatcher,
                configuration,
                registry=platform_registry,
                config_service=self.config_service,
            )
            if platform_database is not None
            else None
        )

    @property
    def enabled(self) -> bool:
        return bool(self.configuration.get("api", "enabled", default=True))

    def handle(self, method: str, path: str, payload, headers, client: str):
        """Compatibility interface used by direct v1.9 service callers."""

        return self.handle_http(method, path, payload, headers, client).legacy()

    def handle_http(
        self,
        method: str,
        path: str,
        payload,
        headers,
        client: str,
    ) -> APIResponse:
        if not self.enabled:
            return APIResponse(404)
        if path.startswith("/api/v2/"):
            if (
                self.platform is None
                or self.configuration.get(
                    "platform",
                    "enabled",
                    default=True,
                )
                is not True
            ):
                return APIResponse(404)
            return self.platform.handle(method, path, payload, headers, client)
        status, response = self._handle_v1(method, path, payload, headers, client)
        return APIResponse(status, response)

    def _handle_v1(self, method: str, path: str, payload, headers, client: str):
        if not self.enabled:
            return 404, None
        if path == "/api/health":
            if method != "GET":
                return 405, None
            return 200, {
                "status": "ok",
                "version": VERSION,
                "uptime_seconds": int(time.monotonic() - self.started),
            }
        source = ""
        if path == "/api/events" and isinstance(payload, dict):
            source = str(payload.get("source") or "").casefold()
        admin_paths = {
            "/api/config",
            "/api/config/validate",
            "/api/logs",
            "/api/preview",
            "/api/test-send",
        }
        principal = self._principal(
            headers,
            source=source,
            require_admin=path in admin_paths,
        )
        if principal is None:
            self.audit.write("anonymous", path, "unauthorized", source)
            return 401, None
        if not self.rate_limiter.allow(principal, client):
            self.audit.write(principal.name, path, "rate_limited", source)
            return 429, {"error": "rate limit exceeded"}
        try:
            status, response = self._authorized(method, path, payload, principal)
        except ValueError as error:
            self.audit.write(principal.name, path, "invalid", source)
            return 400, {"error": self.sanitizer._sanitize_text(error)}
        except Exception:
            self.audit.write(principal.name, path, "failed", source)
            return 500, {"error": "request failed"}
        self.audit.write(principal.name, path, str(status), source)
        return status, response

    def authorize_source(self, headers, source: str, client: str):
        """Authorize a source-specific v1.9 ingestion endpoint."""

        if not self.enabled:
            return None
        principal = self._principal(headers, source=source, require_admin=False)
        if principal is None:
            return None
        if not self.rate_limiter.allow(principal, client):
            return False
        return principal

    def _authorized(self, method, path, payload, principal):
        if path == "/api/events":
            if method != "POST":
                return 405, None
            parsed = self.dispatcher.parse_webhook("event_api", payload)
            if parsed is None or not principal.allows(parsed.source):
                return 403, None
            delivered = self.router.route(parsed)
            return 202, {"accepted": True, "delivered": bool(delivered)}
        if path == "/api/config":
            if method == "GET":
                return 200, {"config": self.config_service.read_masked()}
            if method == "PUT":
                proposed = payload.get("config") if isinstance(payload, dict) else None
                backup = self.config_service.replace(proposed)
                return 200, {"saved": True, "backup": backup.name}
            return 405, None
        if path == "/api/config/validate":
            if method != "POST":
                return 405, None
            proposed = payload.get("config") if isinstance(payload, dict) else None
            errors = self.config_service.validate(proposed)
            return 200, {"valid": not errors, "errors": errors}
        if path == "/api/logs":
            if method != "GET":
                return 405, None
            return 200, {"lines": self._safe_logs()}
        if path in {"/api/preview", "/api/test-send"}:
            if method != "POST" or not isinstance(payload, dict):
                return 405 if method != "POST" else 400, None
            event = payload.get("event")
            parsed = self.dispatcher.parse_webhook("event_api", event)
            if parsed is None:
                raise ValueError("invalid preview event")
            if path == "/api/test-send":
                return 200, {"delivered": bool(self.router.route(parsed))}
            return 200, {"preview": self._preview(parsed, payload.get("output"))}
        return 404, None

    def _principal(self, headers, source: str, require_admin: bool):
        authorization = str(headers.get("Authorization", ""))
        supplied = ""
        if authorization.casefold().startswith("bearer "):
            supplied = authorization[7:].strip()
        if not supplied:
            supplied = str(headers.get("X-Notifinho-Token", ""))
        return self.authenticator.authenticate(
            supplied,
            source=source,
            require_admin=require_admin,
        )

    def _preview(self, notification, output_name) -> dict:
        output = str(output_name or "discord").casefold()
        if output not in {"discord", "teams"}:
            raise ValueError("preview output must be discord or teams")
        destination = DiscordOutput() if output == "discord" else TeamsOutput()
        formatter = destination.source_formatters.get(
            notification.source,
            destination.default_formatter,
        )
        return formatter._sanitize_payload(formatter.format(notification))

    def _safe_logs(self) -> list[str]:
        root = Path(__file__).resolve().parents[2]
        path = root / "logs" / "notifinho.log"
        if not path.is_file():
            return []
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-200:]
        return [self.sanitizer._sanitize_text(line)[:2000] for line in lines]
