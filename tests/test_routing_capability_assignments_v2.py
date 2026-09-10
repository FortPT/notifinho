"""Routing Capabilities V2 API projection contracts."""

from types import SimpleNamespace

from api.platform import PlatformAPI
from storage.ownership import Actor


class _Categories:
    @staticmethod
    def list_overrides():
        return {}


class _Routes:
    def __init__(self, routes):
        self._routes = routes

    def list_visible_safe(self, _actor):
        return list(self._routes), []


def _route(route_id, source, input_type, destination_id, enabled=True):
    return SimpleNamespace(
        id=route_id,
        source=source,
        input_type=input_type,
        destination_id=destination_id,
        enabled=enabled,
    )


def test_integrations_route_capabilities_expose_minimal_assignment_state():
    api = PlatformAPI.__new__(PlatformAPI)
    api.configuration_sync = None
    api.integration_categories = _Categories()
    api.routes = _Routes(
        [
            _route("route-zabbix-a", "zabbix", "http", "destination-a"),
            _route("route-zabbix-b", "zabbix", "http", "destination-b", False),
            _route("route-fallback", "*", "http", "destination-fallback"),
        ]
    )

    response = api._integrations_endpoint(
        "GET",
        None,
        Actor("a" * 32, "admin"),
    )

    assert response.status == 200
    capabilities = {item["id"]: item for item in response.payload["route_options"]}

    assert capabilities["zabbix:http"]["icon_key"] == "zabbix"
    assert capabilities["zabbix:http"]["category"] == "monitoring"
    assert capabilities["zabbix:http"]["assignments"] == [
        {
            "route_id": "route-zabbix-a",
            "destination_id": "destination-a",
            "enabled": True,
        },
        {
            "route_id": "route-zabbix-b",
            "destination_id": "destination-b",
            "enabled": False,
        },
    ]
    assert capabilities["grafana:http"]["assignments"] == []
    assert capabilities["fallback:http"]["admin_only"] is True
    assert capabilities["fallback:http"]["icon_key"] == "generic"
    assert capabilities["fallback:http"]["category"] == "generic"
    assert capabilities["fallback:http"]["assignments"] == [
        {
            "route_id": "route-fallback",
            "destination_id": "destination-fallback",
            "enabled": True,
        }
    ]

    for capability in capabilities.values():
        for assignment in capability["assignments"]:
            assert set(assignment) == {"route_id", "destination_id", "enabled"}
