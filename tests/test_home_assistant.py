"""Authenticated Home Assistant event-contract tests."""

from __future__ import annotations

import copy
import http.client
import json
import threading

from pathlib import Path

import pytest

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


def fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def system_log_fixture() -> dict:
    return json.loads(SYSTEM_LOG_FIXTURE.read_text(encoding="utf-8"))


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
    assert item.metadata["device"] == "sensor.hp_ilo_echo_server_health"
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
    assert item.metadata["device"] == "Noisy"
    assert item.body == "A useful first sentence…"
    assert len(item.body) <= 321


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
