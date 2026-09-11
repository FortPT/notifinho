"""Routing Capabilities V2 catalogue contracts."""

from integrations.catalog import route_options


def test_route_capabilities_have_unique_stable_ids():
    options = route_options()
    capability_ids = [item["id"] for item in options]

    assert len(capability_ids) == len(set(capability_ids))
    assert "xo:smtp" in capability_ids
    assert "zabbix:smtp" in capability_ids
    assert "zabbix:http" in capability_ids
    assert "synology:smtp" in capability_ids
    assert "synology:http" in capability_ids
    assert "dell_idrac:redfish" in capability_ids
    assert "home_assistant:http" in capability_ids
    assert "fallback:smtp" in capability_ids
    assert "fallback:http" in capability_ids
    assert "fallback:redfish" in capability_ids


def test_fallback_capability_identity_does_not_change_matching_contract():
    fallbacks = {
        item["id"]: item
        for item in route_options()
        if item["generic"]
    }

    assert fallbacks == {
        "fallback:smtp": {
            "id": "fallback:smtp",
            "source": "*",
            "input_type": "smtp",
            "integration_name": "Fallback",
            "input_name": "SMTP",
            "label": "Fallback (SMTP)",
            "generic": True,
            "admin_only": True,
        },
        "fallback:http": {
            "id": "fallback:http",
            "source": "*",
            "input_type": "http",
            "integration_name": "Fallback",
            "input_name": "HTTP",
            "label": "Fallback (HTTP)",
            "generic": True,
            "admin_only": True,
        },
        "fallback:redfish": {
            "id": "fallback:redfish",
            "source": "*",
            "input_type": "redfish",
            "integration_name": "Fallback",
            "input_name": "Redfish",
            "label": "Fallback (Redfish)",
            "generic": True,
            "admin_only": True,
        },
    }


def test_only_fallback_capabilities_are_administrator_only():
    options = route_options()

    assert all(item["admin_only"] is item["generic"] for item in options)
