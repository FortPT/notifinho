"""Owned-route delivery orchestration with retries and safe history."""

from __future__ import annotations

import time
import uuid

from dataclasses import dataclass
from typing import Callable

from models import Notification
from storage.database import Database
from storage.destinations import DeliveryDestination, DestinationStore
from storage.ownership import Actor, OwnershipPolicy
from storage.routes import Route, RouteStore
from storage.sanitize import sanitize_text
from storage.secrets import SecretStore


@dataclass(frozen=True)
class DeliveryResult:
    success: bool
    retryable: bool = False
    response_status: int | None = None
    error_code: str = ""
    safe_error: str = ""


@dataclass(frozen=True)
class DeliveryAttempt:
    id: str
    delivery_id: str
    owner_user_id: str
    route_id: str | None
    destination_id: str | None
    source: str
    title: str
    severity: str
    outcome: str
    attempt_number: int
    retryable: bool
    response_status: int | None
    error_code: str
    safe_error: str
    created_at: int
    completed_at: int


@dataclass(frozen=True)
class DeliverySummary:
    matched_routes: int
    delivered: int
    failed: int
    attempts: int

    @property
    def success(self) -> bool:
        return self.delivered > 0 and self.failed == 0


class DeliveryHistoryStore:
    def __init__(
        self,
        database: Database,
        *,
        clock: Callable[[], float] = time.time,
    ):
        self.database = database
        self.clock = clock

    def record(
        self,
        owner_user_id: str,
        delivery_id: str,
        route: Route,
        notification: Notification,
        attempt_number: int,
        outcome: str,
        result: DeliveryResult,
    ) -> DeliveryAttempt:
        if outcome not in {"delivered", "failed", "retry_scheduled"}:
            raise ValueError("unsupported delivery outcome")
        now = int(self.clock())
        attempt_id = uuid.uuid4().hex
        source = self._safe(notification.source, 64)
        title = self._safe(notification.title or notification.subject, 256)
        severity = self._safe(
            (notification.metadata or {}).get("severity") or notification.status,
            64,
        )
        error_code = self._safe(result.error_code, 64)
        safe_error = self._safe(result.safe_error, 500)
        response_status = (
            int(result.response_status) if result.response_status is not None else None
        )
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO delivery_attempts(
                    id, delivery_id, owner_user_id, route_id, destination_id,
                    source, title, severity, outcome, attempt_number,
                    retryable, response_status, error_code, safe_error,
                    created_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt_id,
                    str(delivery_id),
                    str(owner_user_id),
                    route.id,
                    route.destination_id,
                    source,
                    title,
                    severity,
                    outcome,
                    int(attempt_number),
                    1 if result.retryable else 0,
                    response_status,
                    error_code or None,
                    safe_error or None,
                    now,
                    now,
                ),
            )
        return self.get(Actor(str(owner_user_id), "user"), attempt_id)

    def get(self, actor: Actor, attempt_id: str) -> DeliveryAttempt:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM delivery_attempts WHERE id = ?",
                (str(attempt_id),),
            ).fetchone()
        if row is None:
            raise KeyError("delivery attempt not found")
        OwnershipPolicy.require_read(actor, str(row["owner_user_id"]))
        return self._attempt(row)

    def list_visible(self, actor: Actor, limit: int = 100) -> list[DeliveryAttempt]:
        bounded = max(1, min(int(limit), 500))
        with self.database.connect() as connection:
            if actor.is_admin:
                rows = connection.execute(
                    "SELECT * FROM delivery_attempts ORDER BY created_at DESC, id LIMIT ?",
                    (bounded,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM delivery_attempts
                    WHERE owner_user_id = ?
                    ORDER BY created_at DESC, id LIMIT ?
                    """,
                    (actor.user_id, bounded),
                ).fetchall()
        return [self._attempt(row) for row in rows]

    def _safe(self, value, maximum: int) -> str:
        return sanitize_text(value)[:maximum]

    @staticmethod
    def _attempt(row) -> DeliveryAttempt:
        return DeliveryAttempt(
            id=str(row["id"]),
            delivery_id=str(row["delivery_id"]),
            owner_user_id=str(row["owner_user_id"]),
            route_id=str(row["route_id"]) if row["route_id"] is not None else None,
            destination_id=(
                str(row["destination_id"])
                if row["destination_id"] is not None
                else None
            ),
            source=str(row["source"]),
            title=str(row["title"]),
            severity=str(row["severity"]),
            outcome=str(row["outcome"]),
            attempt_number=int(row["attempt_number"]),
            retryable=bool(row["retryable"]),
            response_status=(
                int(row["response_status"])
                if row["response_status"] is not None
                else None
            ),
            error_code=str(row["error_code"] or ""),
            safe_error=str(row["safe_error"] or ""),
            created_at=int(row["created_at"]),
            completed_at=int(row["completed_at"]),
        )


class PlatformDeliveryService:
    """Deliver matching user routes through injected output adapters."""

    def __init__(
        self,
        routes: RouteStore,
        destinations: DestinationStore,
        secrets: SecretStore,
        history: DeliveryHistoryStore,
        adapters: dict[str, Callable],
        *,
        maximum_attempts: int = 3,
        retry_delays: tuple[float, ...] = (0, 1, 5),
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self.routes = routes
        self.destinations = destinations
        self.secrets = secrets
        self.history = history
        self.adapters = dict(adapters)
        self.maximum_attempts = max(1, min(int(maximum_attempts), 5))
        self.retry_delays = tuple(max(0.0, float(value)) for value in retry_delays)
        self.sleeper = sleeper

    def deliver(
        self,
        actor: Actor,
        notification: Notification,
    ) -> DeliverySummary:
        matching = self.routes.matching(actor, actor.user_id, notification)
        delivered = 0
        failed = 0
        attempts = 0
        for route in matching:
            delivery_id = uuid.uuid4().hex
            outcome, count = self._deliver_route(
                actor,
                route,
                notification,
                delivery_id,
            )
            attempts += count
            if outcome:
                delivered += 1
            else:
                failed += 1
        return DeliverySummary(len(matching), delivered, failed, attempts)

    def _deliver_route(
        self,
        actor: Actor,
        route: Route,
        notification: Notification,
        delivery_id: str,
    ) -> tuple[bool, int]:
        try:
            target = self.destinations.for_delivery(actor, route.destination_id)
        except (KeyError, PermissionError):
            result = DeliveryResult(False, error_code="destination_unavailable")
            self.history.record(
                actor.user_id,
                delivery_id,
                route,
                notification,
                1,
                "failed",
                result,
            )
            return False, 1

        secret_value = None
        if target.secret_id is not None:
            try:
                owner_actor = Actor(target.destination.owner_user_id, "user")
                secret_value = self.secrets.resolve(owner_actor, target.secret_id)
            except (KeyError, PermissionError, RuntimeError, ValueError):
                result = DeliveryResult(False, error_code="secret_unavailable")
                self.history.record(
                    actor.user_id,
                    delivery_id,
                    route,
                    notification,
                    1,
                    "failed",
                    result,
                )
                return False, 1

        adapter = self.adapters.get(target.destination.output_type)
        if adapter is None:
            result = DeliveryResult(False, error_code="adapter_unavailable")
            self.history.record(
                actor.user_id,
                delivery_id,
                route,
                notification,
                1,
                "failed",
                result,
            )
            return False, 1

        for attempt_number in range(1, self.maximum_attempts + 1):
            if attempt_number > 1:
                delay_index = min(attempt_number - 1, len(self.retry_delays) - 1)
                delay = self.retry_delays[delay_index] if self.retry_delays else 0
                if delay:
                    self.sleeper(delay)
            result = self._invoke(adapter, target, secret_value, notification)
            retry = result.retryable and attempt_number < self.maximum_attempts
            outcome = (
                "delivered"
                if result.success
                else "retry_scheduled" if retry else "failed"
            )
            self.history.record(
                actor.user_id,
                delivery_id,
                route,
                notification,
                attempt_number,
                outcome,
                result,
            )
            if result.success:
                return True, attempt_number
            if not retry:
                return False, attempt_number
        return False, self.maximum_attempts

    @staticmethod
    def _invoke(adapter, target, secret_value, notification) -> DeliveryResult:
        try:
            result = adapter(target.destination, secret_value, notification)
        except Exception:
            return DeliveryResult(False, retryable=False, error_code="delivery_exception")
        if isinstance(result, DeliveryResult):
            return result
        if isinstance(result, bool):
            return DeliveryResult(result, retryable=False)
        return DeliveryResult(False, retryable=False, error_code="invalid_adapter_result")
