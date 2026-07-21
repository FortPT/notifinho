"""Ownership-safe preview and single-attempt test-delivery service."""

from __future__ import annotations

from models import Notification
from outputs.platform import OutputPreview, PlatformOutputRegistry
from storage.audit_events import AuditEventStore
from storage.delivery import DeliveryResult
from storage.destinations import DestinationStore
from storage.ownership import Actor
from storage.secrets import SecretStore


class PlatformOutputService:
    def __init__(
        self,
        destinations: DestinationStore,
        secrets: SecretStore,
        registry: PlatformOutputRegistry,
        *,
        audit: AuditEventStore | None = None,
    ):
        self.destinations = destinations
        self.secrets = secrets
        self.registry = registry
        self.audit = audit

    def preview(
        self,
        actor: Actor,
        destination_id: str,
        notification: Notification,
    ) -> OutputPreview:
        try:
            destination = self.destinations.get(actor, destination_id)
            adapter = self.registry.get(destination.output_type)
            preview = adapter.preview(destination, notification)
        except PermissionError:
            self._audit(actor, "destination.preview", destination_id, "denied")
            raise PermissionError("destination is not available") from None
        except (KeyError, TypeError, ValueError):
            self._audit(actor, "destination.preview", destination_id, "invalid")
            raise ValueError("destination cannot preview this notification") from None
        self._audit(
            actor,
            "destination.preview",
            destination_id,
            "success",
            {"output_type": destination.output_type},
        )
        return preview

    def test_delivery(
        self,
        actor: Actor,
        destination_id: str,
        notification: Notification,
    ) -> DeliveryResult:
        try:
            target = self.destinations.for_delivery(actor, destination_id)
        except (KeyError, PermissionError):
            result = DeliveryResult(False, error_code="destination_unavailable")
            self._audit_result(actor, destination_id, result)
            return result
        try:
            adapter = self.registry.get(target.destination.output_type)
        except KeyError:
            result = DeliveryResult(False, error_code="adapter_unavailable")
            self._audit_result(actor, destination_id, result)
            return result

        secret_value = None
        if target.secret_id is not None:
            try:
                secret_owner = Actor(target.destination.owner_user_id, "user")
                secret_value = self.secrets.resolve(secret_owner, target.secret_id)
            except (KeyError, PermissionError, RuntimeError, ValueError):
                result = DeliveryResult(False, error_code="secret_unavailable")
                self._audit_result(actor, destination_id, result)
                return result
        try:
            result = adapter.deliver(target.destination, secret_value, notification)
        except Exception:
            result = DeliveryResult(False, error_code="delivery_exception")
        if not isinstance(result, DeliveryResult):
            result = DeliveryResult(False, error_code="invalid_adapter_result")
        self._audit_result(actor, destination_id, result)
        return result

    def _audit_result(self, actor, destination_id, result):
        self._audit(
            actor,
            "destination.test",
            destination_id,
            "success" if result.success else "failed",
            {
                "error_code": result.error_code,
                "response_status": result.response_status,
                "retryable": result.retryable,
            },
        )

    def _audit(self, actor, action, resource_id, outcome, details=None):
        if self.audit is not None:
            self.audit.write(
                actor,
                action,
                "destination",
                resource_id,
                outcome,
                details,
            )
