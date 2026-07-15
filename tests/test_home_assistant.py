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


def fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


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
