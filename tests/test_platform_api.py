"""Authenticated v2 platform API, ownership, and ingestion tests."""

from __future__ import annotations

import json

import pytest

import api.platform as platform_module

from api.security import hash_password
from api.service import APIService
from dispatcher import Dispatcher
from outputs.platform import OutputPreview, PlatformOutputAdapter, PlatformOutputRegistry
from storage.database import Database
from storage.delivery import DeliveryResult
from storage.users import UserStore


PASSWORD = "correct horse battery staple"


class Configuration:
    def __init__(self, data):
        self.data = data

    def get(self, *keys, default=None):
        value = self.data
        for key in keys:
            if not isinstance(value, dict) or key not in value:
                return default
            value = value[key]
        return value


class Router:
    def route(self, _notification):
        raise AssertionError("v2 platform ingestion must not use the YAML router")


class FakeWebhookAdapter(PlatformOutputAdapter):
    output_type = "webhook"

    def __init__(self):
        self.deliveries = []

    def preview(self, destination, notification):
        return OutputPreview(
            "webhook",
            "application/json",
            {
                "schema": "notifinho.event.v1",
                "source": notification.source,
                "title": notification.title,
            },
            {"method": destination.settings["method"]},
        )

    def deliver(self, destination, secret_value, notification):
        self.deliveries.append((destination.id, secret_value, notification.source))
        return DeliveryResult(True, response_status=202)


def fast_hash(password: str) -> str:
    return hash_password(password, salt=b"\x07" * 16, iterations=1_000)


@pytest.fixture
def platform_api(tmp_path, monkeypatch):
    database = Database(tmp_path / "state" / "notifinho.db")
    database.migrate()

    def users(database_value):
        return UserStore(database_value, password_hasher=fast_hash)

    monkeypatch.setattr(platform_module, "UserStore", users)
    seed_users = users(database)
    admin = seed_users.bootstrap_admin("administrator", PASSWORD)
    owner = seed_users.create("owner-user", "owner secure password")
    another = seed_users.create("another-user", "another secure password")
    adapter = FakeWebhookAdapter()
    registry = PlatformOutputRegistry([adapter])
    config = Configuration({
        "api": {"enabled": True},
        "platform": {
            "enabled": True,
            "state_dir": str(tmp_path / "state"),
            "secure_cookies": False,
        },
    })
    service = APIService(
        Dispatcher(),
        Router(),
        config,
        platform_database=database,
        platform_registry=registry,
    )
    return {
        "database": database,
        "admin": admin,
        "owner": owner,
        "another": another,
        "adapter": adapter,
        "service": service,
    }


def call(platform, method, path, payload=None, headers=None, client="127.0.0.1"):
    return platform["service"].handle_http(
        method,
        path,
        payload,
        headers or {},
        client,
    )


def login(platform, username="administrator", password=PASSWORD, client="127.0.0.1"):
    response = call(
        platform,
        "POST",
        "/api/v2/session",
        {"username": username, "password": password},
        client=client,
    )
    assert response.status == 200
    cookies = [value for name, value in response.headers if name == "Set-Cookie"]
    session = next(item.split(";", 1)[0] for item in cookies if "session=" in item)
    return {
        "Cookie": session,
        "X-CSRF-Token": response.payload["csrf_token"],
    }


def create_destination(platform, headers, *, owner_user_id=None, shared=False):
    payload = {
        "name": "Synthetic webhook",
        "output_type": "webhook",
        "settings": {"method": "POST"},
        "shared": shared,
        "secret": {"url": "https://example.invalid/events"},
    }
    if owner_user_id:
        payload["owner_user_id"] = owner_user_id
    response = call(
        platform,
        "POST",
        "/api/v2/destinations",
        payload,
        headers,
    )
    assert response.status == 201
    return response.payload["destination"]


def create_route(platform, headers, destination_id, *, owner_user_id=None):
    payload = {
        "name": "Synthetic route",
        "source": "home_lab",
        "destination_id": destination_id,
        "filters": {"severities": ["warning"]},
    }
    if owner_user_id:
        payload["owner_user_id"] = owner_user_id
    response = call(platform, "POST", "/api/v2/routes", payload, headers)
    assert response.status == 201
    return response.payload["route"]


def create_token(platform, headers, *, owner_user_id=None, scopes=("home_lab",)):
    payload = {
        "name": "Synthetic application",
        "source_scopes": list(scopes),
        "rate_limit_per_minute": 10,
    }
    if owner_user_id:
        payload["owner_user_id"] = owner_user_id
    response = call(platform, "POST", "/api/v2/tokens", payload, headers)
    assert response.status == 201
    return response.payload


def event(source="home_lab", severity="warning"):
    return {
        "schema": "notifinho.event.v1",
        "source": source,
        "title": "Synthetic platform event",
        "message": "Owner-scoped API validation.",
        "severity": severity,
        "status": "active",
    }


def test_login_session_cookie_and_csrf_boundary(platform_api):
    denied = call(
        platform_api,
        "POST",
        "/api/v2/session",
        {"username": "administrator", "password": "incorrect password"},
    )
    assert denied.status == 401
    assert denied.payload == {"error": "invalid credentials"}

    headers = login(platform_api)
    current = call(platform_api, "GET", "/api/v2/session", headers=headers)
    missing_csrf = call(
        platform_api,
        "POST",
        "/api/v2/tokens",
        {"name": "blocked", "source_scopes": ["source"]},
        {"Cookie": headers["Cookie"]},
    )
    logout = call(platform_api, "DELETE", "/api/v2/session", headers=headers)

    assert current.status == 200
    assert current.payload["user"]["role"] == "admin"
    assert missing_csrf.status == 401
    assert logout.status == 204
    assert len([item for item in logout.headers if item[0] == "Set-Cookie"]) == 2
    assert call(platform_api, "GET", "/api/v2/session", headers=headers).status == 401


def test_secure_cookie_defaults_use_host_prefix_and_strict_attributes(platform_api):
    platform_api["service"].configuration.data["platform"]["secure_cookies"] = True
    response = call(
        platform_api,
        "POST",
        "/api/v2/session",
        {"username": "administrator", "password": PASSWORD},
        client="127.0.0.9",
    )
    cookies = [value for name, value in response.headers if name == "Set-Cookie"]

    assert any(item.startswith("__Host-notifinho_session=") for item in cookies)
    assert any(item.startswith("__Host-notifinho_csrf=") for item in cookies)
    assert all("Secure" in item and "SameSite=Strict" in item for item in cookies)
    assert "HttpOnly" in next(item for item in cookies if "session=" in item)
    assert "HttpOnly" not in next(item for item in cookies if "csrf=" in item)


def test_admin_portability_preview_apply_and_v1_secret_redaction(platform_api):
    admin_headers = login(platform_api)
    user_headers = login(
        platform_api,
        "owner-user",
        "owner secure password",
        client="127.0.0.8",
    )
    denied = call(
        platform_api,
        "GET",
        "/api/v2/portability/export",
        headers=user_headers,
    )
    document = {
        "schema": "notifinho.platform.v1",
        "destinations": [],
        "routes": [],
    }
    preview = call(
        platform_api,
        "POST",
        "/api/v2/portability/preview",
        {"document": document},
        admin_headers,
    )
    imported = call(
        platform_api,
        "POST",
        "/api/v2/portability/import",
        {
            "document": document,
            "fingerprint": preview.payload["preview"]["fingerprint"],
            "confirm": True,
        },
        admin_headers,
    )
    yaml_source = """
outputs:
  discord:
    default:
      webhook: https://discord.com/api/webhooks/123/api-private
routing:
  grafana:
    output: discord
    target: default
"""
    migration_preview = call(
        platform_api,
        "POST",
        "/api/v2/migrations/v1/preview",
        {"yaml": yaml_source},
        admin_headers,
    )
    serialized = json.dumps(migration_preview.payload, sort_keys=True)
    migration = call(
        platform_api,
        "POST",
        "/api/v2/migrations/v1/import",
        {
            "yaml": yaml_source,
            "fingerprint": migration_preview.payload["preview"]["fingerprint"],
            "confirm": True,
        },
        admin_headers,
    )
    exported = call(
        platform_api,
        "GET",
        "/api/v2/portability/export",
        headers=admin_headers,
    )

    assert denied.status == 403
    assert preview.status == 200 and preview.payload["preview"]["valid"] is True
    assert imported.status == 200
    assert migration_preview.status == 200
    assert "api-private" not in serialized
    assert migration.status == 200
    assert migration.payload["import"]["destinations_created"] == 1
    assert exported.status == 200
    assert "api-private" not in json.dumps(exported.payload, sort_keys=True)


def test_admin_mounted_configuration_bridge_endpoints_are_confirmed(platform_api):
    class Plan:
        def public(self):
            return {
                "valid": True,
                "fingerprint": "a" * 64,
                "warnings": [],
                "errors": [],
                "summary": {"destinations": 1, "routes": 1},
            }

    class Bridge:
        def inventory(self, _actor):
            return {
                "authority": "yaml",
                "summary": {"inputs": 2, "outputs": 1, "routes": 1},
            }

        def preview(self, _actor):
            return Plan(), self.inventory(_actor), ("safe preview",)

        def activate(self, _actor, fingerprint):
            assert fingerprint == "a" * 64
            return {
                "destinations_created": 1,
                "routes_created": 1,
                "authority": "database",
            }

        def set_authority(self, _actor, authority, confirmation):
            assert confirmation == "USE YAML ROUTING"
            return {"previous": "database", "authority": authority}

    platform_api["service"].platform.configuration_bridge = Bridge()
    admin_headers = login(platform_api)
    user_headers = login(
        platform_api,
        "owner-user",
        "owner secure password",
        client="127.0.0.21",
    )

    inventory = call(
        platform_api,
        "GET",
        "/api/v2/configuration/inventory",
        headers=admin_headers,
    )
    denied = call(
        platform_api,
        "GET",
        "/api/v2/configuration/inventory",
        headers=user_headers,
    )
    preview = call(
        platform_api,
        "POST",
        "/api/v2/configuration/migration/preview",
        {},
        admin_headers,
    )
    missing_confirmation = call(
        platform_api,
        "POST",
        "/api/v2/configuration/migration/apply",
        {"fingerprint": "a" * 64, "confirm": False},
        admin_headers,
    )
    applied = call(
        platform_api,
        "POST",
        "/api/v2/configuration/migration/apply",
        {"fingerprint": "a" * 64, "confirm": True},
        admin_headers,
    )
    fallback = call(
        platform_api,
        "PUT",
        "/api/v2/configuration/routing-authority",
        {"authority": "yaml", "confirmation": "USE YAML ROUTING"},
        admin_headers,
    )

    assert inventory.status == 200
    assert inventory.payload["configuration"]["authority"] == "yaml"
    assert denied.status == 403
    assert preview.status == 200
    assert preview.payload["preview"]["warnings"] == ["safe preview"]
    assert missing_confirmation.status == 400
    assert applied.payload["migration"]["authority"] == "database"
    assert fallback.payload["routing"]["authority"] == "yaml"


def test_admin_backup_restore_is_confirmed_and_revokes_http_session(platform_api):
    headers = login(platform_api)
    created = call(
        platform_api,
        "POST",
        "/api/v2/backups",
        {},
        headers,
    )
    backup_id = created.payload["backup"]["id"]
    listed = call(platform_api, "GET", "/api/v2/backups", headers=headers)
    denied = call(
        platform_api,
        "POST",
        f"/api/v2/backups/{backup_id}/restore",
        {"confirmation": "wrong"},
        headers,
    )
    restored = call(
        platform_api,
        "POST",
        f"/api/v2/backups/{backup_id}/restore",
        {"confirmation": backup_id},
        headers,
    )

    assert created.status == 201
    assert listed.status == 200 and listed.payload["backups"][0]["id"] == backup_id
    assert denied.status == 400
    assert restored.status == 200
    assert restored.payload["restore"]["sessions_revoked"] is True
    assert len([item for item in restored.headers if item[0] == "Set-Cookie"]) == 2
    assert call(platform_api, "GET", "/api/v2/session", headers=headers).status == 401


def test_user_administration_and_password_resets_revoke_sessions(platform_api):
    admin_headers = login(platform_api)
    created = call(
        platform_api,
        "POST",
        "/api/v2/users",
        {"username": "api-user", "password": "api user secure password", "role": "user"},
        admin_headers,
    )
    user_id = created.payload["user"]["id"]
    user_headers = login(
        platform_api,
        "api-user",
        "api user secure password",
        client="127.0.0.2",
    )
    forbidden = call(platform_api, "GET", "/api/v2/users", headers=user_headers)
    reset = call(
        platform_api,
        "PUT",
        f"/api/v2/users/{user_id}/password",
        {"password": "replacement secure password"},
        admin_headers,
    )

    assert created.status == 201
    assert forbidden.status == 403
    assert reset.status == 200
    assert call(platform_api, "GET", "/api/v2/session", headers=user_headers).status == 401


def test_administrator_cannot_reset_own_password_from_user_administration(platform_api):
    headers = login(platform_api)
    denied = call(
        platform_api,
        "PUT",
        f"/api/v2/users/{platform_api['admin'].id}/password",
        {"password": "replacement administrator password"},
        headers,
    )

    assert denied.status == 403
    assert login(
        platform_api,
        "administrator",
        PASSWORD,
        client="127.0.0.33",
    )


def test_current_user_password_change_requires_password_and_revokes_session(platform_api):
    headers = login(
        platform_api,
        "owner-user",
        "owner secure password",
    )
    denied = call(
        platform_api,
        "PUT",
        "/api/v2/account/password",
        {
            "current_password": "incorrect password",
            "new_password": "replacement owner password",
        },
        headers,
    )
    changed = call(
        platform_api,
        "PUT",
        "/api/v2/account/password",
        {
            "current_password": "owner secure password",
            "new_password": "replacement owner password",
        },
        headers,
        client="127.0.0.2",
    )

    assert denied.status == 403
    assert changed.status == 204
    assert call(platform_api, "GET", "/api/v2/session", headers=headers).status == 401
    assert login(
        platform_api,
        "owner-user",
        "replacement owner password",
        client="127.0.0.3",
    )


def test_tokens_are_one_time_scoped_rotatable_and_revocable(platform_api):
    headers = login(platform_api)
    created = create_token(platform_api, headers)
    token_id = created["token"]["id"]
    first_value = created["value"]
    listed = call(platform_api, "GET", "/api/v2/tokens", headers=headers)
    rotated = call(
        platform_api,
        "POST",
        f"/api/v2/tokens/{token_id}/rotate",
        {},
        headers,
    )
    second_value = rotated.payload["value"]

    assert first_value != second_value
    assert "value" not in json.dumps(listed.payload)
    assert rotated.payload["token"]["version"] == 2
    assert call(
        platform_api,
        "POST",
        "/api/v2/events",
        event(),
        {"Authorization": f"Bearer {first_value}"},
    ).status == 401

    revoked = call(
        platform_api,
        "POST",
        f"/api/v2/tokens/{token_id}/revoke",
        {},
        headers,
    )
    assert revoked.payload["token"]["revoked_at"] is not None
    assert call(
        platform_api,
        "POST",
        "/api/v2/events",
        event(),
        {"Authorization": f"Bearer {second_value}"},
    ).status == 401


def test_administrator_can_list_another_owners_tokens_and_routes(platform_api):
    headers = login(platform_api)
    owner_id = platform_api["owner"].id
    destination = create_destination(
        platform_api,
        headers,
        owner_user_id=owner_id,
    )
    create_route(
        platform_api,
        headers,
        destination["id"],
        owner_user_id=owner_id,
    )
    create_token(platform_api, headers, owner_user_id=owner_id)

    tokens = call(
        platform_api,
        "GET",
        f"/api/v2/users/{owner_id}/tokens",
        headers=headers,
    )
    routes = call(
        platform_api,
        "GET",
        f"/api/v2/users/{owner_id}/routes",
        headers=headers,
    )

    assert tokens.status == 200
    assert tokens.payload["tokens"][0]["owner_user_id"] == owner_id
    assert "value" not in tokens.payload["tokens"][0]
    assert routes.status == 200
    assert routes.payload["routes"][0]["owner_user_id"] == owner_id

def test_owned_event_submission_routes_through_platform_adapters(platform_api):
    headers = login(platform_api)
    destination = create_destination(platform_api, headers)
    create_route(platform_api, headers, destination["id"])
    credentials = create_token(platform_api, headers)

    accepted = call(
        platform_api,
        "POST",
        "/api/v2/events",
        event(),
        {"Authorization": f"Bearer {credentials['value']}"},
    )
    denied = call(
        platform_api,
        "POST",
        "/api/v2/events",
        event(source="another_source"),
        {"Authorization": f"Bearer {credentials['value']}"},
        client="127.0.0.2",
    )
    history = call(platform_api, "GET", "/api/v2/deliveries", headers=headers)

    assert accepted.status == 202
    assert accepted.payload == {
        "accepted": True,
        "matched": 1,
        "delivered": 1,
        "failed": 0,
        "attempts": 1,
    }
    assert denied.status == 401
    assert history.payload["deliveries"][0]["outcome"] == "delivered"
    assert platform_api["adapter"].deliveries[0][1] == (
        b'{"url":"https://example.invalid/events"}'
    )


def test_platform_event_tokens_apply_source_and_client_rate_limits(platform_api):
    headers = login(platform_api)
    created = call(
        platform_api,
        "POST",
        "/api/v2/tokens",
        {
            "name": "One request token",
            "source_scopes": ["home_lab"],
            "rate_limit_per_minute": 1,
        },
        headers,
    )
    bearer = {"Authorization": f"Bearer {created.payload['value']}"}

    first = call(platform_api, "POST", "/api/v2/events", event(), bearer)
    second = call(platform_api, "POST", "/api/v2/events", event(), bearer)
    other_client = call(
        platform_api,
        "POST",
        "/api/v2/events",
        event(),
        bearer,
        client="127.0.0.2",
    )

    assert first.status == 202
    assert second.status == 429
    assert other_client.status == 202


def test_session_event_submission_requires_csrf(platform_api):
    headers = login(platform_api)
    missing = call(
        platform_api,
        "POST",
        "/api/v2/events",
        event(),
        {"Cookie": headers["Cookie"]},
    )
    accepted = call(
        platform_api,
        "POST",
        "/api/v2/events",
        event(),
        headers,
        client="127.0.0.2",
    )

    assert missing.status == 401
    assert accepted.status == 202
    assert accepted.payload["matched"] == 0


def test_destination_secrets_are_write_only_and_shared_use_keeps_owner_secret(platform_api):
    admin_headers = login(platform_api)
    owner_id = platform_api["owner"].id
    destination = create_destination(
        platform_api,
        admin_headers,
        owner_user_id=owner_id,
        shared=True,
    )
    owner_headers = login(
        platform_api,
        "owner-user",
        "owner secure password",
        client="127.0.0.2",
    )
    another_headers = login(
        platform_api,
        "another-user",
        "another secure password",
        client="127.0.0.3",
    )

    visible = call(platform_api, "GET", "/api/v2/destinations", headers=another_headers)
    preview = call(
        platform_api,
        "POST",
        f"/api/v2/destinations/{destination['id']}/preview",
        {"event": event()},
        another_headers,
    )
    delivered = call(
        platform_api,
        "POST",
        f"/api/v2/destinations/{destination['id']}/test",
        {"event": event()},
        another_headers,
    )
    denied_update = call(
        platform_api,
        "PATCH",
        f"/api/v2/destinations/{destination['id']}",
        {"enabled": False},
        another_headers,
    )
    owner_update = call(
        platform_api,
        "PATCH",
        f"/api/v2/destinations/{destination['id']}",
        {"secret": {"url": "https://example.invalid/rotated"}},
        owner_headers,
    )

    encoded = json.dumps(visible.payload) + json.dumps(preview.payload)
    assert "example.invalid" not in encoded
    assert visible.payload["destinations"][0]["secret_configured"] is True
    assert delivered.payload["result"]["success"] is True
    assert denied_update.status == 403
    assert owner_update.status == 200


def test_route_update_revalidates_ownership_filters_and_enabled_type(platform_api):
    headers = login(platform_api)
    destination = create_destination(platform_api, headers)
    route = create_route(platform_api, headers, destination["id"])
    updated = call(
        platform_api,
        "PATCH",
        f"/api/v2/routes/{route['id']}",
        {"priority": 10, "filters": {"hosts": ["vm-*"]}, "enabled": False},
        headers,
    )
    invalid = call(
        platform_api,
        "PATCH",
        f"/api/v2/routes/{route['id']}",
        {"enabled": "false"},
        headers,
    )

    assert updated.status == 200
    assert updated.payload["route"]["priority"] == 10
    assert updated.payload["route"]["filters"] == {"hosts": ["vm-*"]}
    assert updated.payload["route"]["enabled"] is False
    assert invalid.status == 400


def test_notices_avatar_and_application_lifecycle_are_exposed_safely(
    platform_api,
    monkeypatch,
):
    admin_headers = login(platform_api)
    user_headers = login(
        platform_api,
        "owner-user",
        "owner secure password",
        client="127.0.0.2",
    )
    created = call(
        platform_api,
        "POST",
        "/api/v2/notices",
        {"name": "Maintenance", "message": "Starts at 22:00", "status": "warning"},
        admin_headers,
    )
    visible = call(platform_api, "GET", "/api/v2/notices", headers=user_headers)
    notice = next(item for item in visible.payload["notices"] if item["name"] == "Maintenance")
    dismissed = call(
        platform_api,
        "POST",
        f"/api/v2/notices/{notice['id']}/dismiss",
        {},
        user_headers,
    )
    after = call(platform_api, "GET", "/api/v2/notices", headers=user_headers)

    assert created.status == 201
    assert dismissed.status == 204
    assert notice["id"] not in {item["id"] for item in after.payload["notices"]}

    png = "data:image/png;base64,iVBORw0KGgo="
    avatar = call(
        platform_api,
        "PUT",
        "/api/v2/account/avatar",
        {"image_data": png},
        user_headers,
    )
    assert avatar.status == 200 and avatar.payload["user"]["avatar_data"] == png
    removed = call(
        platform_api,
        "DELETE",
        "/api/v2/account/avatar",
        {},
        user_headers,
    )
    assert removed.status == 200 and removed.payload["user"]["avatar_data"] is None

    token = create_token(platform_api, admin_headers)
    token_id = token["token"]["id"]
    disabled = call(
        platform_api,
        "PATCH",
        f"/api/v2/tokens/{token_id}",
        {"enabled": False},
        admin_headers,
    )
    deleted = call(
        platform_api,
        "DELETE",
        f"/api/v2/tokens/{token_id}",
        {},
        admin_headers,
    )
    assert disabled.status == 200 and disabled.payload["token"]["enabled"] is False
    assert deleted.status == 204

    monkeypatch.setenv("NOTIFINHO_AVAILABLE_VERSION", "99.0.0")
    update = call(platform_api, "GET", "/api/v2/notices", headers=user_headers)
    persistent = next(item for item in update.payload["notices"] if item["kind"] == "update")
    denied = call(
        platform_api,
        "POST",
        f"/api/v2/notices/{persistent['id']}/dismiss",
        {},
        user_headers,
    )
    assert denied.status == 403
    monkeypatch.delenv("NOTIFINHO_AVAILABLE_VERSION")
    resolved = call(platform_api, "GET", "/api/v2/notices", headers=user_headers)
    assert persistent["id"] not in {item["id"] for item in resolved.payload["notices"]}


def test_audit_visibility_and_database_exclude_submitted_credentials(platform_api):
    headers = login(platform_api)
    create_destination(platform_api, headers)
    audit = call(platform_api, "GET", "/api/v2/audit-events", headers=headers)
    database_bytes = platform_api["database"].path.read_bytes()

    assert audit.status == 200
    assert audit.payload["audit_events"]
    assert b"https://example.invalid/events" not in database_bytes
    assert "https://example.invalid/events" not in json.dumps(audit.payload)


def test_invalid_destination_does_not_leave_state_or_secret_records(platform_api):
    headers = login(platform_api)
    response = call(
        platform_api,
        "POST",
        "/api/v2/destinations",
        {
            "name": "Invalid destination",
            "output_type": "mqtt",
            "settings": {"unknown": True},
            "secret": {"password": "must-not-persist"},
        },
        headers,
    )
    with platform_api["database"].connect() as connection:
        destinations = connection.execute("SELECT COUNT(*) FROM destinations").fetchone()[0]
        secrets = connection.execute("SELECT COUNT(*) FROM secret_records").fetchone()[0]

    assert response.status == 400
    assert (destinations, secrets) == (0, 0)
    assert b"must-not-persist" not in platform_api["database"].path.read_bytes()


def test_rejected_multifield_destination_patch_is_non_partial(platform_api):
    admin_headers = login(platform_api)
    destination = create_destination(
        platform_api,
        admin_headers,
        owner_user_id=platform_api["owner"].id,
    )
    owner_headers = login(
        platform_api,
        "owner-user",
        "owner secure password",
        client="127.0.0.2",
    )
    rejected = call(
        platform_api,
        "PATCH",
        f"/api/v2/destinations/{destination['id']}",
        {"settings": {"method": "PUT"}, "shared": True},
        owner_headers,
    )
    current = call(
        platform_api,
        "GET",
        f"/api/v2/destinations/{destination['id']}",
        headers=owner_headers,
    )

    assert rejected.status == 403
    assert current.payload["destination"]["settings"]["method"] == "POST"
    assert current.payload["destination"]["shared"] is False


def test_secret_can_be_attached_later_without_becoming_readable(platform_api):
    headers = login(platform_api)
    created = call(
        platform_api,
        "POST",
        "/api/v2/destinations",
        {
            "name": "Credentials later",
            "output_type": "webhook",
            "settings": {"method": "POST"},
        },
        headers,
    )
    destination_id = created.payload["destination"]["id"]
    updated = call(
        platform_api,
        "PATCH",
        f"/api/v2/destinations/{destination_id}",
        {"secret": {"url": "https://example.invalid/later"}},
        headers,
    )
    fetched = call(
        platform_api,
        "GET",
        f"/api/v2/destinations/{destination_id}",
        headers=headers,
    )

    assert created.payload["destination"]["secret_configured"] is False
    assert updated.payload["destination"]["secret_configured"] is True
    assert "example.invalid" not in json.dumps(fetched.payload)


def test_platform_api_is_absent_without_initialized_platform_database():
    config = Configuration({"api": {"enabled": True}, "platform": {"enabled": False}})
    service = APIService(Dispatcher(), Router(), config)

    assert service.handle_http(
        "POST",
        "/api/v2/session",
        {"username": "administrator", "password": PASSWORD},
        {},
        "127.0.0.1",
    ).status == 404


def test_first_run_bootstrap_creates_admin_session_and_consumes_token(
    tmp_path,
    monkeypatch,
):
    database = Database(tmp_path / "state" / "notifinho.db")
    database.migrate()

    def users(database_value):
        return UserStore(database_value, password_hasher=fast_hash)

    monkeypatch.setattr(platform_module, "UserStore", users)
    config = Configuration({
        "api": {"enabled": True},
        "platform": {"enabled": True, "secure_cookies": False},
    })
    service = APIService(
        Dispatcher(),
        Router(),
        config,
        platform_database=database,
    )
    credential = service.platform.bootstrap.rotate_for_startup()

    status = service.handle_http(
        "GET", "/api/v2/bootstrap", None, {}, "127.0.0.1"
    )
    denied = service.handle_http(
        "POST",
        "/api/v2/bootstrap",
        {"token": "wrong", "username": "administrator", "password": PASSWORD},
        {},
        "127.0.0.1",
    )
    created = service.handle_http(
        "POST",
        "/api/v2/bootstrap",
        {
            "token": credential.token,
            "username": "administrator",
            "password": PASSWORD,
        },
        {},
        "127.0.0.1",
    )
    repeated = service.handle_http(
        "POST",
        "/api/v2/bootstrap",
        {
            "token": credential.token,
            "username": "another-admin",
            "password": "another secure password",
        },
        {},
        "127.0.0.1",
    )

    assert status.status == 200
    assert status.payload["required"] is True
    assert status.payload["expires_at"] == credential.expires_at
    assert denied.status == 401
    assert created.status == 200
    assert created.payload["user"]["role"] == "admin"
    assert any(name == "Set-Cookie" for name, _value in created.headers)
    assert repeated.status == 409
    assert credential.token.encode() not in database.path.read_bytes()
    assert users(database).count() == 1


def test_integrations_endpoint_is_complete_and_categories_are_database_backed(platform_api):
    headers = login(platform_api)
    listed = call(platform_api, "GET", "/api/v2/integrations", headers=headers)
    assert listed.status == 200
    integrations_by_source = {
        item["source"]: item for item in listed.payload["integrations"]
    }
    assert [item["id"] for item in integrations_by_source["zabbix"]["inputs"]] == [
        "smtp",
        "http",
    ]
    assert integrations_by_source["dell_idrac"]["inputs"] == [
        {"id": "redfish", "name": "Redfish"}
    ]
    labels = {item["label"] for item in listed.payload["route_options"]}
    assert "Fallback (HTTP)" in labels
    assert "Fallback (Redfish)" in labels

    updated = call(
        platform_api,
        "PUT",
        "/api/v2/integrations",
        {"source": "zabbix", "category": "applications"},
        headers,
    )
    assert updated.status == 200
    changed = next(
        item for item in updated.payload["integrations"]
        if item["source"] == "zabbix"
    )
    assert changed["category"] == "generic"


def test_route_api_round_trips_input_type(platform_api):
    headers = login(platform_api)
    destination = create_destination(platform_api, headers)
    response = call(
        platform_api,
        "POST",
        "/api/v2/routes",
        {
            "name": "Zabbix SMTP route",
            "source": "zabbix",
            "input_type": "smtp",
            "destination_id": destination["id"],
            "filters": {},
        },
        headers,
    )
    assert response.status == 201
    assert response.payload["route"]["source"] == "zabbix"
    assert response.payload["route"]["input_type"] == "smtp"


def test_unexpected_platform_error_returns_safe_reference(platform_api, monkeypatch):
    headers = login(platform_api)

    def broken():
        raise RuntimeError("synthetic private failure")

    monkeypatch.setattr(
        platform_api["service"].platform.integration_categories,
        "list_overrides",
        broken,
    )
    response = call(platform_api, "GET", "/api/v2/integrations", headers=headers)
    assert response.status == 500
    assert response.payload["code"] == "internal_error"
    assert response.payload["path"] == "/api/v2/integrations"
    assert len(response.payload["reference"]) == 12
    assert "synthetic private failure" not in response.payload["error"]


def test_resource_list_errors_are_isolated_per_destination_and_route(platform_api):
    headers = login(platform_api)
    broken_destination = create_destination(platform_api, headers)
    second = call(
        platform_api,
        "POST",
        "/api/v2/destinations",
        {
            "name": "Second webhook",
            "output_type": "webhook",
            "settings": {"method": "POST"},
            "shared": True,
            "secret": {"url": "https://example.invalid/second"},
        },
        headers,
    ).payload["destination"]
    broken_route = create_route(platform_api, headers, broken_destination["id"])
    second_route = call(
        platform_api,
        "POST",
        "/api/v2/routes",
        {
            "name": "Second route",
            "source": "zabbix",
            "input_type": "smtp",
            "destination_id": second["id"],
            "filters": {},
        },
        headers,
    ).payload["route"]

    with platform_api["database"].transaction() as connection:
        connection.execute(
            "UPDATE destinations SET settings_json = 'not-json' WHERE id = ?",
            (broken_destination["id"],),
        )
        connection.execute(
            "UPDATE routes SET filters_json = 'not-json' WHERE id = ?",
            (broken_route["id"],),
        )

    destinations = call(platform_api, "GET", "/api/v2/destinations", headers=headers)
    routes = call(platform_api, "GET", "/api/v2/routes", headers=headers)

    assert destinations.status == 200
    assert [item["id"] for item in destinations.payload["destinations"]] == [second["id"]]
    assert destinations.payload["errors"][0]["resource_id"] == broken_destination["id"]
    assert routes.status == 200
    assert [item["id"] for item in routes.payload["routes"]] == [second_route["id"]]
    assert routes.payload["errors"][0]["resource_id"] == broken_route["id"]
