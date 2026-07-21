"""Authenticated Home Assistant event-contract tests."""

from __future__ import annotations

import copy
import http.client
import json
import threading

from pathlib import Path

import pytest

from config import config
from dispatcher import Dispatcher
from formatters.discord_home_assistant import HomeAssistantDiscordFormatter
from formatters.teams_home_assistant import HomeAssistantTeamsFormatter
from inputs.http import HTTPServer
from outputs.discord import DiscordOutput
from outputs.teams import TeamsOutput
from parsers.home_assistant import Parser


FIXTURE = Path(__file__).parent / "fixtures" / "home_assistant" / "automation_warning.json"
SYSTEM_LOG_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "home_assistant"
    / "system_log_chromecast.json"
)
KASA_LOG_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "home_assistant"
    / "system_log_kasa.json"
)
IPP_LOG_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "home_assistant"
    / "system_log_ipp.json"
)


def fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def system_log_fixture() -> dict:
    return json.loads(SYSTEM_LOG_FIXTURE.read_text(encoding="utf-8"))


def kasa_log_fixture() -> dict:
    return json.loads(KASA_LOG_FIXTURE.read_text(encoding="utf-8"))


def ipp_log_fixture() -> dict:
    return json.loads(IPP_LOG_FIXTURE.read_text(encoding="utf-8"))


class Router:
    def __init__(self):
        self.items = []

    def route(self, item):
        self.items.append(item)
        return True


def post(port, payload, token=""):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Notifinho-Token"] = token
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    connection.request("POST", "/home-assistant/events", json.dumps(payload), headers)
    response = connection.getresponse()
    status = response.status
    response.read()
    connection.close()
    return status


def test_home_assistant_contract_normalizes_automation_event():
    item = Parser().parse(fixture())
    assert item.source == "home_assistant"
    assert item.category == "environment"
    assert item.status == "warning"
    assert item.metadata["entity_id"] == "sensor.utility_room_humidity"
    assert item.metadata["area"] == "Utility room"
    assert item.metadata["action_link"].startswith("https://")


def test_home_assistant_system_log_is_normalized_for_readable_cards():
    item = Parser().parse(system_log_fixture())

    assert item.title == "TV-01 error"
    assert item.body == "Failed to connect to service"
    assert item.metadata["service"] == "Chromecast"
    assert item.metadata["device"] == "TV-01"
    assert item.metadata["endpoint"] == "192.168.0.128:8009"
    assert item.metadata["retry_seconds"] == "5.0"
    assert "/usr/local/lib" not in item.body
    assert "MDNSServiceInfo" not in item.body
    assert "BRAVIA-4K" not in item.body


def test_home_assistant_generic_errors_use_service_and_concise_event_details():
    payload = {
        "schema": "notifinho.home_assistant.v1",
        "title": "Home Assistant error",
        "message": (
            "State '{bios_hardware: {status: OK}, fans: {status: Not Installed}}' "
            "for sensor.hp_ilo_echo_server_health is longer than 255, "
            "falling back to unknown"
        ),
        "severity": "error",
        "category": "system_error",
        "event_type": "system_log",
        "component": "homeassistant.core",
        "device": "Home Assistant",
        "tags": ["error"],
    }

    item = Parser().parse(payload)

    assert item.metadata["service"] == "Core"
    assert item.metadata["device"] == ""
    assert item.metadata["entity_id"] == "sensor.hp_ilo_echo_server_health"
    assert "255-character limit" in item.body
    assert "bios_hardware" not in item.body


def test_home_assistant_unknown_error_message_is_bounded_for_cards():
    payload = system_log_fixture()
    payload.update(
        title="Home Assistant error · noisy.component",
        component="homeassistant.components.noisy.worker",
        message="A useful first sentence. " + ("verbose internal details " * 100),
        device="Home Assistant",
    )

    item = Parser().parse(payload)

    assert item.title == "Noisy error"
    assert item.metadata["service"] == "Noisy"
    assert item.metadata["device"] == ""
    assert item.body == "A useful first sentence…"
    assert len(item.body) <= 321


def test_home_assistant_kasa_error_uses_endpoint_alias_and_structured_details():
    aliases = {
        "endpoints": {
            "192.168.103.35": {
                "device": "HUB-01 | Hall Floor 1",
            },
        },
    }

    item = Parser(aliases=aliases).parse(kasa_log_fixture())

    assert item.title == "HUB-01 | Hall Floor 1 error"
    assert item.body == "Failed to query the TriggerLogs module."
    assert item.metadata["service"] == "Tapo"
    assert item.metadata["device"] == "HUB-01 | Hall Floor 1"
    assert item.metadata["endpoint"] == "192.168.103.35"
    assert item.metadata["error_code"] == "UNSPECIFIC_ERROR (-1001)"
    assert "control_child" not in item.body


def test_home_assistant_ipp_error_uses_component_alias_and_concise_details():
    aliases = {
        "components": {
            "homeassistant.components.ipp.coordinator": {
                "device": "PRT-01 | Floor 1",
                "endpoint": "192.168.101.157",
            },
        },
    }

    item = Parser(aliases=aliases).parse(ipp_log_fixture())

    assert item.title == "PRT-01 | Floor 1 error"
    assert item.body == "Failed to communicate with the IPP server."
    assert item.metadata["service"] == "Internet Printing Protocol"
    assert item.metadata["device"] == "PRT-01 | Floor 1"
    assert item.metadata["endpoint"] == "192.168.101.157"


def test_home_assistant_aliases_are_loaded_from_application_config(monkeypatch):
    monkeypatch.setitem(
        config._data,
        "home_assistant",
        {
            "aliases": {
                "endpoints": {
                    "192.168.103.35": {
                        "device": "Configured hub",
                    },
                },
            },
        },
    )

    item = Parser().parse(kasa_log_fixture())

    assert item.metadata["device"] == "Configured hub"


def test_home_assistant_unknown_service_is_not_presented_as_a_device():
    item = Parser().parse({
        "schema": "notifinho.home_assistant.v1",
        "title": "Home Assistant error",
        "message": "Calendar synchronization failed.",
        "severity": "error",
        "status": "active",
        "category": "system_error",
        "event_type": "system_log",
        "component": "homeassistant.components.calendar.worker",
        "device": "Home Assistant",
        "tags": ["home-assistant", "error"],
    })

    assert item.title == "Calendar error"
    assert item.metadata["service"] == "Calendar"
    assert item.metadata["device"] == ""


@pytest.mark.parametrize(
    "mutation",
    (
        lambda value: value.update(schema="wrong"),
        lambda value: value.update(title=""),
        lambda value: value.update(entity_id="invalid"),
        lambda value: value.update(tags=["x"] * 33),
        lambda value: value.update(message="x" * 4001),
    ),
)
def test_invalid_home_assistant_events_are_rejected(mutation):
    value = copy.deepcopy(fixture())
    mutation(value)
    assert Parser.is_envelope(value) is False
    assert Dispatcher().parse_webhook("home_assistant", value) is None


def test_home_assistant_endpoint_requires_authentication_and_routes():
    router = Router()
    server = HTTPServer(
        ("127.0.0.1", 0), Dispatcher(), router, 1_048_576, "synthetic-ha-secret"
    )
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        missing = post(server.server_port, fixture())
        accepted = post(server.server_port, fixture(), "synthetic-ha-secret")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert (missing, accepted) == (401, 204)
    assert [item.source for item in router.items] == ["home_assistant"]


def test_home_assistant_formatters_are_registered_and_safe():
    item = Parser().parse(fixture())
    discord = HomeAssistantDiscordFormatter().format(item)
    teams = HomeAssistantTeamsFormatter().format(item)
    rendered = json.dumps({"discord": discord, "teams": teams})
    assert isinstance(DiscordOutput().source_formatters["home_assistant"], HomeAssistantDiscordFormatter)
    assert isinstance(TeamsOutput().source_formatters["home_assistant"], HomeAssistantTeamsFormatter)
    assert "Utility room" in rendered
    assert "sensor.utility_room_humidity" in rendered
    assert "Home Assistant" in rendered


def test_home_assistant_formatters_present_service_device_and_retry_separately():
    item = Parser().parse(system_log_fixture())
    discord = HomeAssistantDiscordFormatter().format(item)
    teams = HomeAssistantTeamsFormatter().format(item)
    rendered = json.dumps({"discord": discord, "teams": teams})

    assert "Chromecast" in rendered
    assert "TV-01" in rendered
    assert "192.168.0.128:8009" in rendered
    assert "Retrying in 5.0 seconds" in rendered
    assert "System Error" in rendered
    assert "System_Error" not in rendered
    assert "/usr/local/lib" not in rendered
    assert "MDNSServiceInfo" not in rendered
    assert "BRAVIA-4K" not in rendered


def test_home_assistant_formatters_present_structured_error_code():
    aliases = {
        "endpoints": {
            "192.168.103.35": {
                "device": "HUB-01 | Hall Floor 1",
            },
        },
    }
    item = Parser(aliases=aliases).parse(kasa_log_fixture())
    rendered = json.dumps({
        "discord": HomeAssistantDiscordFormatter().format(item),
        "teams": HomeAssistantTeamsFormatter().format(item),
    })

    assert "UNSPECIFIC_ERROR (-1001)" in rendered
    assert "192.168.103.35" in rendered
    assert "control_child" not in rendered


def test_home_assistant_discord_string_tags_are_not_split_into_characters():
    item = Parser().parse(fixture())
    item.metadata["tags"] = "office, temperature"
    embed = HomeAssistantDiscordFormatter().format(item)["embeds"][0]
    details = next(
        field
        for field in embed["fields"]
        if "📋 **Event details**" in field["value"]
    )

    assert "🏷️ **Tags:** office, temperature" in details["value"]
    assert "o, f, f, i, c, e" not in details["value"]
