"""User-scoped token, destination, route, and audit service tests."""

from __future__ import annotations

import pytest

from api.security import RateLimiter, hash_password
from models import Notification
from storage.api_tokens import APITokenStore
from storage.audit_events import AuditEventStore
from storage.database import Database
from storage.destinations import DestinationStore
from storage.routes import RouteStore
from storage.secrets import SecretStore
from storage.users import UserStore


class Clock:
    def __init__(self, value=1_800_000_000):
        self.value = value

    def __call__(self):
        return self.value


def fast_hash(password: str) -> str:
    return hash_password(password, salt=b"\x03" * 16, iterations=1_000)


@pytest.fixture
def platform(tmp_path):
    database = Database(tmp_path / "state" / "notifinho.db")
    database.migrate()
    clock = Clock()
    users = UserStore(database, clock=clock, password_hasher=fast_hash)
    admin = users.bootstrap_admin("administrator", "correct horse battery staple")
    owner = users.create("owner-user", "owner secure password")
    another = users.create("another-user", "another secure password")
    audit = AuditEventStore(database, clock=clock)
    secrets = SecretStore(database, clock=clock)
    tokens = APITokenStore(database, audit=audit, clock=clock)
    destinations = DestinationStore(database, audit=audit, clock=clock)
    routes = RouteStore(database, audit=audit, clock=clock)
    return {
        "database": database,
        "clock": clock,
        "users": users,
        "admin": admin,
        "owner": owner,
        "another": another,
        "audit": audit,
        "secrets": secrets,
        "tokens": tokens,
        "destinations": destinations,
        "routes": routes,
    }


def test_api_token_value_is_one_time_hashed_and_source_scoped(platform):
    owner = platform["owner"]
    tokens = platform["tokens"]
    database = platform["database"]
    credentials = tokens.create(
        owner.actor,
        owner.id,
        "Home automation",
        source_scopes=["home_assistant", "grafana"],
        rate_limit_per_minute=2,
    )

    assert credentials.value.startswith("ntf_")
    assert not hasattr(credentials.token, "token_hash")
    assert credentials.token.source_scopes == ("home_assistant", "grafana")
    assert credentials.value.encode() not in database.path.read_bytes()
    assert tokens.authenticate(credentials.value, "home_assistant") is not None
    assert tokens.authenticate(credentials.value, "qnap") is None
    assert tokens.authenticate("wrong", "home_assistant") is None

    principal = tokens.authenticate(credentials.value, "grafana")
    limiter = RateLimiter(clock=lambda: 0)
    assert limiter.allow(principal, "192.0.2.1") is True
    assert limiter.allow(principal, "192.0.2.1") is True
    assert limiter.allow(principal, "192.0.2.1") is False


def test_token_rotation_invalidates_previous_value_and_revoke_is_final(platform):
    owner = platform["owner"]
    tokens = platform["tokens"]
    created = tokens.create(
        owner.actor,
        owner.id,
        "Application",
        source_scopes=["grafana"],
    )
    rotated = tokens.rotate(owner.actor, created.token.id)

    assert rotated.token.version == 2
    assert rotated.value != created.value
    assert tokens.authenticate(created.value, "grafana") is None
    assert tokens.authenticate(rotated.value, "grafana") is not None

    revoked = tokens.revoke(owner.actor, created.token.id)
    assert revoked.revoked_at == platform["clock"].value
    assert tokens.authenticate(rotated.value, "grafana") is None
    with pytest.raises(ValueError, match="revoked"):
        tokens.rotate(owner.actor, created.token.id)


def test_token_admin_and_wildcard_scopes_require_administrator(platform):
    owner = platform["owner"]
    admin = platform["admin"]
    tokens = platform["tokens"]

    with pytest.raises(PermissionError, match="wildcard"):
        tokens.create(owner.actor, owner.id, "Wildcard", source_scopes=["*"])
    with pytest.raises(PermissionError, match="administrator tokens"):
        tokens.create(
            owner.actor,
            owner.id,
            "Admin",
            role="admin",
            source_scopes=["grafana"],
        )

    created = tokens.create(
        admin.actor,
        admin.id,
        "Infrastructure admin",
        role="admin",
        source_scopes=["*"],
    )
    principal = tokens.authenticate(created.value, "anything")
    assert principal is not None
    assert principal.token_role == "admin"


def test_expired_and_disabled_owner_tokens_cannot_authenticate(platform):
    owner = platform["owner"]
    tokens = platform["tokens"]
    credentials = tokens.create(
        owner.actor,
        owner.id,
        "Temporary",
        source_scopes=["grafana"],
        expires_at=platform["clock"].value + 10,
    )
    platform["clock"].value += 11
    assert tokens.authenticate(credentials.value, "grafana") is None

    active = tokens.create(
        owner.actor,
        owner.id,
        "Active",
        source_scopes=["grafana"],
    )
    platform["users"].set_enabled(owner.id, False)
    assert tokens.authenticate(active.value, "grafana") is None


def test_destination_metadata_separates_secrets_and_rejects_secret_settings(platform):
    owner = platform["owner"]
    another = platform["another"]
    secrets = platform["secrets"]
    destinations = platform["destinations"]
    secret = secrets.create(
        owner.actor,
        owner.id,
        "Discord webhook",
        "discord_webhook",
        "https://discord.invalid/api/webhooks/private/value",
    )
    destination = destinations.create(
        owner.actor,
        owner.id,
        "Operations Discord",
        "discord",
        secret_id=secret.id,
        settings={"components_v2": True},
    )

    assert destination.secret_configured is True
    assert not hasattr(destination, "secret_id")
    assert "private/value" not in repr(destination)
    with pytest.raises(PermissionError):
        destinations.get(another.actor, destination.id)
    with pytest.raises(ValueError, match="owner-scoped secret"):
        destinations.create(
            owner.actor,
            owner.id,
            "Unsafe",
            "discord",
            settings={"nested": {"webhook_url": "private"}},
        )


def test_destination_cannot_use_another_users_secret(platform):
    owner = platform["owner"]
    another = platform["another"]
    secret = platform["secrets"].create(
        another.actor,
        another.id,
        "Private",
        "webhook",
        "private",
    )
    with pytest.raises(PermissionError, match="same owner"):
        platform["destinations"].create(
            owner.actor,
            owner.id,
            "Cross owner",
            "webhook",
            secret_id=secret.id,
        )


def test_only_admin_can_share_destinations_and_shared_routes_are_explicit(platform):
    admin = platform["admin"]
    owner = platform["owner"]
    another = platform["another"]
    destinations = platform["destinations"]
    routes = platform["routes"]
    secret = platform["secrets"].create(
        admin.actor,
        admin.id,
        "Shared webhook",
        "webhook",
        "shared-private-value",
    )
    with pytest.raises(PermissionError, match="administrators"):
        destinations.create(
            owner.actor,
            owner.id,
            "User shared",
            "webhook",
            shared=True,
        )
    shared = destinations.create(
        admin.actor,
        admin.id,
        "Shared infrastructure",
        "webhook",
        secret_id=secret.id,
        shared=True,
    )
    route = routes.create(
        another.actor,
        another.id,
        "Shared Grafana",
        "grafana",
        shared.id,
    )
    assert route.destination_id == shared.id
    assert shared.id in {item.id for item in destinations.list_visible(another.actor)}
    with pytest.raises(ValueError, match="another user's route"):
        destinations.set_shared(admin.actor, shared.id, False)


def test_private_destination_cannot_be_used_by_another_users_route(platform):
    owner = platform["owner"]
    another = platform["another"]
    destination = platform["destinations"].create(
        owner.actor,
        owner.id,
        "Private destination",
        "ntfy",
    )
    with pytest.raises(PermissionError, match="owned by the user or shared"):
        platform["routes"].create(
            another.actor,
            another.id,
            "Invalid route",
            "grafana",
            destination.id,
        )


def test_route_filters_match_source_host_event_severity_and_status(platform):
    owner = platform["owner"]
    destination = platform["destinations"].create(
        owner.actor,
        owner.id,
        "Filtered",
        "ntfy",
    )
    route = platform["routes"].create(
        owner.actor,
        owner.id,
        "Critical backup route",
        "grafana",
        destination.id,
        filters={
            "hosts": ["PVE-01"],
            "events": ["backup*"],
            "severities": ["critical"],
            "statuses": ["active"],
        },
        priority=10,
    )
    matching = Notification(
        source="grafana",
        title="Backup failure",
        status="failure",
        metadata={
            "host": "pve-01",
            "event_type": "backup_failed",
            "severity": "Critical",
            "state": "active",
        },
    )
    assert platform["routes"].matches(route, matching) is True

    matching.metadata["host"] = "pve-02"
    assert platform["routes"].matches(route, matching) is False
    matching.metadata["host"] = "pve-01"
    matching.metadata["severity"] = "warning"
    assert platform["routes"].matches(route, matching) is False


def test_matching_routes_are_owner_scoped_ordered_and_respect_enabled_state(platform):
    owner = platform["owner"]
    another = platform["another"]
    destinations = platform["destinations"]
    routes = platform["routes"]
    first_destination = destinations.create(
        owner.actor, owner.id, "First", "ntfy"
    )
    second_destination = destinations.create(
        owner.actor, owner.id, "Second", "ntfy"
    )
    another_destination = destinations.create(
        another.actor, another.id, "Other", "ntfy"
    )
    second = routes.create(
        owner.actor, owner.id, "Second", "grafana", second_destination.id, priority=20
    )
    first = routes.create(
        owner.actor, owner.id, "First", "grafana", first_destination.id, priority=10
    )
    routes.create(
        another.actor,
        another.id,
        "Other",
        "grafana",
        another_destination.id,
        priority=1,
    )

    notification = Notification(source="grafana", title="Synthetic")
    assert [item.id for item in routes.matching(owner.actor, owner.id, notification)] == [
        first.id,
        second.id,
    ]
    routes.set_enabled(owner.actor, first.id, False)
    destinations.set_enabled(owner.actor, second_destination.id, False)
    assert routes.matching(owner.actor, owner.id, notification) == []


def test_audit_events_are_scoped_and_sensitive_details_are_redacted(platform):
    owner = platform["owner"]
    another = platform["another"]
    audit = platform["audit"]
    audit.write(
        owner.actor,
        "token.inspect",
        "api_token",
        "synthetic",
        "success",
        {"token": "private", "note": "safe"},
    )

    owner_events = audit.list_visible(owner.actor)
    other_events = audit.list_visible(another.actor)
    admin_events = audit.list_visible(platform["admin"].actor)
    assert owner_events[0].details == {"note": "safe", "token": "<redacted>"}
    assert all(item.actor_user_id == owner.id for item in owner_events)
    assert other_events == []
    assert len(admin_events) >= len(owner_events)
