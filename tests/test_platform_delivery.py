"""Owned-route delivery, retry, secret, and safe-history tests."""

from __future__ import annotations

import pytest

from api.security import hash_password
from models import Notification
from storage.database import Database
from storage.delivery import (
    DeliveryHistoryStore,
    DeliveryResult,
    PlatformDeliveryService,
)
from storage.destinations import DestinationStore
from storage.routes import RouteStore
from storage.secrets import SecretStore
from storage.users import UserStore


def fast_hash(password: str) -> str:
    return hash_password(password, salt=b"\x04" * 16, iterations=1_000)


@pytest.fixture
def delivery_platform(tmp_path):
    database = Database(tmp_path / "state" / "notifinho.db")
    database.migrate()
    users = UserStore(database, password_hasher=fast_hash)
    admin = users.bootstrap_admin("administrator", "correct horse battery staple")
    owner = users.create("owner-user", "owner secure password")
    another = users.create("another-user", "another secure password")
    secrets = SecretStore(database)
    destinations = DestinationStore(database)
    routes = RouteStore(database)
    history = DeliveryHistoryStore(database)
    return {
        "database": database,
        "users": users,
        "admin": admin,
        "owner": owner,
        "another": another,
        "secrets": secrets,
        "destinations": destinations,
        "routes": routes,
        "history": history,
    }


def configured_route(platform, *, output_type="webhook", owner_key="owner"):
    owner = platform[owner_key]
    secret = platform["secrets"].create(
        owner.actor,
        owner.id,
        f"{owner.username} delivery credential",
        "webhook",
        f"private-value-for-{owner.username}",
    )
    destination = platform["destinations"].create(
        owner.actor,
        owner.id,
        f"{owner.username} destination",
        output_type,
        secret_id=secret.id,
        settings={"mode": "synthetic"},
    )
    route = platform["routes"].create(
        owner.actor,
        owner.id,
        f"{owner.username} route",
        "grafana",
        destination.id,
    )
    return owner, destination, route


def test_delivery_uses_matching_owner_route_and_resolves_secret_internally(
    delivery_platform,
):
    owner, destination, route = configured_route(delivery_platform)
    observed = []

    def adapter(target, secret, notification):
        observed.append((target, secret, notification))
        return DeliveryResult(True, response_status=204)

    service = PlatformDeliveryService(
        delivery_platform["routes"],
        delivery_platform["destinations"],
        delivery_platform["secrets"],
        delivery_platform["history"],
        {"webhook": adapter},
        sleeper=lambda _delay: None,
    )
    notification = Notification(
        source="grafana",
        title="Synthetic warning",
        status="warning",
        metadata={"severity": "warning"},
    )
    summary = service.deliver(owner.actor, notification)

    assert summary.success is True
    assert (summary.matched_routes, summary.delivered, summary.failed) == (1, 1, 0)
    assert observed[0][0].id == destination.id
    assert observed[0][1] == f"private-value-for-{owner.username}".encode()
    attempt = delivery_platform["history"].list_visible(owner.actor)[0]
    assert attempt.route_id == route.id
    assert attempt.outcome == "delivered"
    assert attempt.response_status == 204
    assert "private-value" not in repr(attempt)


def test_retryable_delivery_records_each_attempt_and_bounded_delays(delivery_platform):
    owner, _destination, _route = configured_route(delivery_platform)
    responses = [
        DeliveryResult(
            False,
            retryable=True,
            response_status=503,
            error_code="upstream_unavailable",
            safe_error="Temporary upstream failure",
        ),
        DeliveryResult(False, retryable=True, response_status=429),
        DeliveryResult(True, response_status=204),
    ]
    delays = []

    def adapter(_target, _secret, _notification):
        return responses.pop(0)

    service = PlatformDeliveryService(
        delivery_platform["routes"],
        delivery_platform["destinations"],
        delivery_platform["secrets"],
        delivery_platform["history"],
        {"webhook": adapter},
        maximum_attempts=3,
        retry_delays=(0, 1, 5),
        sleeper=delays.append,
    )
    summary = service.deliver(
        owner.actor,
        Notification(source="grafana", title="Retry test"),
    )
    attempts = sorted(
        delivery_platform["history"].list_visible(owner.actor),
        key=lambda item: item.attempt_number,
    )

    assert summary == type(summary)(1, 1, 0, 3)
    assert [item.outcome for item in attempts] == [
        "retry_scheduled",
        "retry_scheduled",
        "delivered",
    ]
    assert [item.response_status for item in attempts] == [503, 429, 204]
    assert delays == [1.0, 5.0]


def test_nonretryable_failure_is_recorded_once(delivery_platform):
    owner, _destination, _route = configured_route(delivery_platform)
    service = PlatformDeliveryService(
        delivery_platform["routes"],
        delivery_platform["destinations"],
        delivery_platform["secrets"],
        delivery_platform["history"],
        {
            "webhook": lambda *_args: DeliveryResult(
                False,
                retryable=False,
                response_status=400,
                error_code="invalid_request",
                safe_error="Request rejected",
            )
        },
        sleeper=lambda _delay: None,
    )
    summary = service.deliver(
        owner.actor,
        Notification(source="grafana", title="Failure test"),
    )
    attempts = delivery_platform["history"].list_visible(owner.actor)

    assert (summary.delivered, summary.failed, summary.attempts) == (0, 1, 1)
    assert attempts[0].outcome == "failed"
    assert attempts[0].error_code == "invalid_request"


def test_adapter_exceptions_do_not_reach_safe_history(delivery_platform):
    owner, _destination, _route = configured_route(delivery_platform)

    def adapter(*_args):
        raise RuntimeError("secret internal exception value")

    service = PlatformDeliveryService(
        delivery_platform["routes"],
        delivery_platform["destinations"],
        delivery_platform["secrets"],
        delivery_platform["history"],
        {"webhook": adapter},
    )
    service.deliver(owner.actor, Notification(source="grafana", title="Exception"))
    attempt = delivery_platform["history"].list_visible(owner.actor)[0]

    assert attempt.error_code == "delivery_exception"
    assert attempt.safe_error == ""
    assert "internal exception" not in repr(attempt)


def test_history_sanitizes_credentials_and_never_stores_secret_values(
    delivery_platform,
):
    owner, _destination, _route = configured_route(delivery_platform)
    service = PlatformDeliveryService(
        delivery_platform["routes"],
        delivery_platform["destinations"],
        delivery_platform["secrets"],
        delivery_platform["history"],
        {
            "webhook": lambda *_args: DeliveryResult(
                False,
                safe_error="token=private-token password=hunter2",
            )
        },
    )
    service.deliver(
        owner.actor,
        Notification(
            source="grafana",
            title="authorization=Bearer private-value",
        ),
    )
    attempt = delivery_platform["history"].list_visible(owner.actor)[0]
    raw_database = delivery_platform["database"].path.read_bytes()

    assert "private-token" not in attempt.safe_error
    assert "hunter2" not in attempt.safe_error
    assert "private-value" not in attempt.title
    assert b"private-token" not in raw_database
    assert b"hunter2" not in raw_database


def test_delivery_and_history_are_owner_scoped(delivery_platform):
    owner, _destination, _route = configured_route(delivery_platform)
    another = delivery_platform["another"]
    calls = []
    service = PlatformDeliveryService(
        delivery_platform["routes"],
        delivery_platform["destinations"],
        delivery_platform["secrets"],
        delivery_platform["history"],
        {"webhook": lambda *_args: calls.append(True) or True},
    )
    notification = Notification(source="grafana", title="Owner scoped")

    assert service.deliver(another.actor, notification).matched_routes == 0
    assert service.deliver(owner.actor, notification).delivered == 1
    assert calls == [True]
    assert delivery_platform["history"].list_visible(another.actor) == []
    assert len(delivery_platform["history"].list_visible(owner.actor)) == 1
    assert len(delivery_platform["history"].list_visible(
        delivery_platform["admin"].actor
    )) == 1


def test_shared_destination_can_deliver_without_revealing_owner_secret(
    delivery_platform,
):
    admin = delivery_platform["admin"]
    another = delivery_platform["another"]
    secret = delivery_platform["secrets"].create(
        admin.actor,
        admin.id,
        "Shared delivery secret",
        "webhook",
        "shared-private-value",
    )
    destination = delivery_platform["destinations"].create(
        admin.actor,
        admin.id,
        "Shared destination",
        "webhook",
        secret_id=secret.id,
        shared=True,
    )
    delivery_platform["routes"].create(
        another.actor,
        another.id,
        "Use shared destination",
        "grafana",
        destination.id,
    )
    observed = []
    service = PlatformDeliveryService(
        delivery_platform["routes"],
        delivery_platform["destinations"],
        delivery_platform["secrets"],
        delivery_platform["history"],
        {"webhook": lambda _target, value, _event: observed.append(value) or True},
    )

    assert service.deliver(
        another.actor,
        Notification(source="grafana", title="Shared"),
    ).success is True
    assert observed == [b"shared-private-value"]
    with pytest.raises(PermissionError):
        delivery_platform["secrets"].resolve(another.actor, secret.id)


def test_missing_adapter_is_a_safe_terminal_failure(delivery_platform):
    owner, _destination, _route = configured_route(
        delivery_platform,
        output_type="ntfy",
    )
    service = PlatformDeliveryService(
        delivery_platform["routes"],
        delivery_platform["destinations"],
        delivery_platform["secrets"],
        delivery_platform["history"],
        {},
    )
    summary = service.deliver(owner.actor, Notification(source="grafana"))
    attempt = delivery_platform["history"].list_visible(owner.actor)[0]

    assert summary.failed == 1
    assert attempt.error_code == "adapter_unavailable"
