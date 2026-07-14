"""Production Portainer Alerting webhook integration tests."""

from __future__ import annotations

import copy
import http.client
import json
import threading

from pathlib import Path

import pytest

import router as router_module

from dispatcher import Dispatcher
from formatters.discord_portainer import PortainerDiscordFormatter
from formatters.teams_portainer import PortainerTeamsFormatter
from inputs.http import HTTPServer
from outputs.discord import DiscordOutput
from outputs.teams import TeamsOutput
from parsers.portainer import Parser
from router import Router


FIXTURE = Path(__file__).parent / "fixtures" / "portainer" / "alert_firing.json"


def fixture_payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class RecordingRouter:
    def __init__(self):
        self.notifications = []

    def route(self, notification):
        self.notifications.append(notification)
        return True


class RunningServer:
    def __init__(self, shared_secret=""):
        self.router = RecordingRouter()
        self.server = HTTPServer(
            ("127.0.0.1", 0),
            Dispatcher(),
            self.router,
            1_048_576,
            shared_secret,
        )
        self.thread = threading.Thread(target=self.server.serve_forever)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    @property
    def port(self):
        return self.server.server_port


def request(port, target, payload, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    connection.request(
        "POST",
        target,
        body=json.dumps(payload).encode("utf-8"),
        headers=headers or {"Content-Type": "application/json"},
    )
    response = connection.getresponse()
    status = response.status
    response.read()
    connection.close()
    return status


def test_verified_firing_payload_is_normalized():
    notifications = Parser().parse(fixture_payload())

    assert len(notifications) == 1
    item = notifications[0]
    assert item.source == "portainer"
    assert item.category == "security"
    assert item.status == "warning"
    assert item.title == "High authentication failures for a single user"
    assert item.body == "Authentication failures exceeded the configured threshold."
    assert item.start_time == "2026-07-14T15:45:00Z"
    assert item.end_time == ""
    assert item.metadata["state"] == "firing"
    assert item.metadata["severity"] == "warning"
    assert item.metadata["authentication_method"] == "local"
    assert item.metadata["username"] == "notifinho-discovery-test"
    assert item.metadata["parser_confidence"] == "high"


def test_resolved_payload_maps_to_success_and_end_time():
    payload = fixture_payload()
    payload["status"] = "resolved"
    payload["alerts"][0]["status"] = "resolved"
    payload["alerts"][0]["labels"]["status"] = "resolved"
    payload["alerts"][0]["endsAt"] = "2026-07-14T15:50:00Z"

    item = Parser().parse(payload)[0]

    assert item.status == "success"
    assert item.metadata["state"] == "resolved"
    assert item.end_time == "2026-07-14T15:50:00Z"


def test_critical_firing_payload_maps_to_failure():
    payload = fixture_payload()
    payload["alerts"][0]["labels"]["severity"] = "critical"
    payload["commonLabels"]["severity"] = "critical"

    assert Parser().parse(payload)[0].status == "failure"


def test_grouped_alerts_create_one_notification_per_alert():
    payload = fixture_payload()
    second = copy.deepcopy(payload["alerts"][0])
    second["labels"]["summary"] = "Second synthetic Portainer alert"
    payload["alerts"].append(second)

    notifications = Parser().parse(payload)

    assert [item.title for item in notifications] == [
        "High authentication failures for a single user",
        "Second synthetic Portainer alert",
    ]
    assert {item.metadata["alert_count"] for item in notifications} == {2}


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"status": "firing", "alerts": []},
        {
            "status": "firing",
            "alerts": [{"status": "firing", "labels": {}, "annotations": {}}],
            "commonLabels": {},
            "commonAnnotations": {},
        },
    ],
)
def test_false_positive_alertmanager_payloads_are_rejected(payload):
    assert Parser.is_envelope(payload) is False
    assert Dispatcher().parse_webhook("portainer", payload) is None


def test_portainer_query_token_authenticates_and_routes():
    token = "synthetic-portainer-shared-secret"
    with RunningServer(shared_secret=token) as running:
        missing = request(running.port, "/portainer/alerts", fixture_payload())
        wrong = request(
            running.port,
            "/portainer/alerts?token=wrong",
            fixture_payload(),
        )
        duplicate = request(
            running.port,
            f"/portainer/alerts?token={token}&token={token}",
            fixture_payload(),
        )
        success = request(
            running.port,
            f"/portainer/alerts?token={token}",
            fixture_payload(),
        )

    assert (missing, wrong, duplicate, success) == (401, 401, 401, 204)
    assert [item.source for item in running.router.notifications] == ["portainer"]


def test_portainer_http_logs_do_not_expose_payload_values(caplog):
    payload = fixture_payload()
    caplog.set_level("INFO", logger="notifinho.tests")
    with RunningServer() as running:
        assert request(running.port, "/portainer/alerts", payload) == 204

    rendered = caplog.text
    assert "Detected Portainer Alerting webhook" in rendered
    for private_value in (
        payload["commonLabels"]["username"],
        payload["commonLabels"]["instance"],
        payload["commonLabels"]["alert_rule_id"],
        payload["alerts"][0]["fingerprint"],
    ):
        assert private_value not in rendered


def test_dedicated_formatters_are_registered():
    assert isinstance(
        DiscordOutput().source_formatters["portainer"],
        PortainerDiscordFormatter,
    )


def test_router_uses_portainer_source_key(monkeypatch):
    calls = []

    class Config:
        def get(self, *keys, default=None):
            if keys == ("routing", "portainer"):
                return {"outputs": [{"output": "discord", "target": "portainer"}]}
            return default

    class Output:
        def send(self, item, target):
            calls.append((item.source, target))
            return True

    monkeypatch.setattr(router_module, "config", Config())
    router = Router()
    router.outputs = {"discord": Output()}

    assert router.route(Parser().parse(fixture_payload())[0]) is True
    assert calls == [("portainer", "portainer")]
    assert isinstance(
        TeamsOutput().source_formatters["portainer"],
        PortainerTeamsFormatter,
    )


def test_discord_and_teams_cards_show_useful_fields_and_hide_ids():
    payload = fixture_payload()
    item = Parser().parse(payload)[0]
    discord = PortainerDiscordFormatter().format(item)
    teams = PortainerTeamsFormatter().format(item)
    rendered = json.dumps({"discord": discord, "teams": teams})

    assert "Portainer" in rendered
    assert "Firing" in rendered
    assert "Warning" in rendered
    assert "notifinho-discovery-test" in rendered
    assert "Authentication failures exceeded" in rendered
    for hidden in (
        payload["commonLabels"]["alert_rule_id"],
        payload["alerts"][0]["fingerprint"],
        payload["alerts"][0]["generatorURL"],
        payload["externalURL"],
        payload["groupKey"],
    ):
        assert hidden not in rendered


def test_formatter_text_limits_are_enforced():
    item = Parser().parse(fixture_payload())[0]
    item.title = "T" * 800
    item.body = "B" * 8000
    discord = PortainerDiscordFormatter().format(item)["embeds"][0]
    teams = PortainerTeamsFormatter().format(item)["attachments"][0]["content"]

    assert len(discord["title"]) <= 256
    assert len(discord["fields"][0]["value"]) <= 1024
    assert len(teams["body"][0]["text"]) <= 512
    assert len(teams["body"][2]["items"][0]["text"]) <= 4000
