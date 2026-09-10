"""Routing V2 assignment-oriented creation contract."""

from types import SimpleNamespace

from api.platform import PlatformAPI
from storage.ownership import Actor


class _AllowAllLimiter:
    @staticmethod
    def allow(_principal, _client):
        return True


class _Destinations:
    def __init__(self):
        self.destination = SimpleNamespace(
            id="d" * 32,
            name="Operations Discord",
        )

    def get(self, _actor, destination_id):
        assert destination_id == self.destination.id
        return self.destination


class _Routes:
    def __init__(self):
        self.created = None

    def create(
        self,
        actor,
        owner_user_id,
        name,
        source,
        destination_id,
        *,
        input_type="",
        filters=None,
        priority=100,
        enabled=True,
    ):
        self.created = {
            "actor": actor,
            "owner_user_id": owner_user_id,
            "name": name,
            "source": source,
            "destination_id": destination_id,
            "input_type": input_type,
            "filters": filters,
            "priority": priority,
            "enabled": enabled,
        }
        return SimpleNamespace(
            id="r" * 32,
            destination_id=destination_id,
            enabled=enabled,
        )


def test_post_route_assignment_resolves_capability_and_creates_compatible_route():
    actor = Actor("a" * 32, "user")
    principal = SimpleNamespace(
        session_id="session",
        role="user",
        actor=actor,
    )
    api = PlatformAPI.__new__(PlatformAPI)
    api.session_limiter = _AllowAllLimiter()
    api._session = lambda _headers, require_csrf: principal
    api.destinations = _Destinations()
    api.routes = _Routes()

    response = api.handle(
        "POST",
        "/api/v2/route-assignments",
        {
            "capability_id": "zabbix:http",
            "destination_id": "d" * 32,
            "enabled": True,
        },
        {},
        "127.0.0.1",
    )

    assert response.status == 201
    assert response.payload == {
        "assignment": {
            "route_id": "r" * 32,
            "capability_id": "zabbix:http",
            "destination_id": "d" * 32,
            "enabled": True,
        }
    }
    assert api.routes.created["actor"] == actor
    assert api.routes.created["owner_user_id"] == actor.user_id
    assert api.routes.created["source"] == "zabbix"
    assert api.routes.created["input_type"] == "http"
    assert api.routes.created["destination_id"] == "d" * 32
    assert api.routes.created["filters"] == {}
    assert api.routes.created["priority"] == "normal"
    assert api.routes.created["enabled"] is True
    assert "Zabbix (HTTP)" in api.routes.created["name"]
    assert "Operations Discord" in api.routes.created["name"]
