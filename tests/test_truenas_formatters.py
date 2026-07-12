"""TrueNAS formatter, output-selection, routing, and payload-budget tests."""

from __future__ import annotations

import json

from email import policy
from email.parser import BytesParser
from pathlib import Path

import pytest

import outputs.discord as discord_output_module
import outputs.teams as teams_output_module
import router as router_module

from formatters.discord_truenas import TrueNASDiscordFormatter
from formatters.teams_truenas import TrueNASTeamsFormatter
from models import Notification
from outputs.discord import DiscordOutput
from outputs.teams import TeamsOutput
from parsers.truenas import Parser
from router import Router
from version import VERSION


FIXTURES = Path(__file__).parent / "fixtures" / "truenas"


def fixture_notification(name: str = "grouped_alerts.eml"):
    with (FIXTURES / name).open("rb") as fixture:
        return Parser().parse(BytesParser(policy=policy.default).parse(fixture))


def test_discord_and_teams_payloads_contain_operational_details():
    notification = fixture_notification()
    discord = TrueNASDiscordFormatter().format(notification)
    teams = TrueNASTeamsFormatter().format(notification)
    for expected in (
        "SYNTHETIC-TRUENAS",
        "SYNTHETIC-POOL",
        "SYNTHETIC-REPLICATION",
        "Cleared",
        "Severity",
        f"Notifinho v{VERSION}",
    ):
        assert expected in json.dumps(discord)
        assert expected in json.dumps(teams)


@pytest.mark.parametrize(
    ("status", "discord_color", "teams_color"),
    [
        ("failure", 0xE74C3C, "Attention"),
        ("warning", 0xF39C12, "Warning"),
        ("success", 0x2ECC71, "Good"),
        ("information", 0x3498DB, "Accent"),
    ],
)
def test_normalized_status_colors(status, discord_color, teams_color):
    notification = Notification(
        source="truenas",
        category="system",
        status=status,
        title="Synthetic event",
        body="Synthetic message",
        metadata={"host": "SYNTHETIC-TRUENAS", "severity": status},
    )
    embed = TrueNASDiscordFormatter().format(notification)["embeds"][0]
    card = TrueNASTeamsFormatter().format(notification)["attachments"][0]["content"]
    assert embed["color"] == discord_color
    assert card["body"][0]["color"] == teams_color


def test_outputs_register_truenas_without_replacing_existing_formatters():
    discord = DiscordOutput()
    teams = TeamsOutput()
    assert isinstance(discord.source_formatters["truenas"], TrueNASDiscordFormatter)
    assert isinstance(teams.source_formatters["truenas"], TrueNASTeamsFormatter)
    assert {"grafana", "qnap", "zabbix"} <= set(discord.source_formatters)
    assert {"grafana", "qnap", "zabbix"} <= set(teams.source_formatters)


@pytest.mark.parametrize(
    ("output_class", "output_module", "payload_key"),
    [
        (DiscordOutput, discord_output_module, "embeds"),
        (TeamsOutput, teams_output_module, "attachments"),
    ],
)
def test_actual_output_selects_truenas_formatter_without_network(
    monkeypatch, output_class, output_module, payload_key
):
    captured = {}

    class Config:
        def get(self, *keys, default=None):
            return "https://example.invalid/synthetic/webhook" if keys[-1:] == ("webhook",) else default

    class Response:
        status_code = 204
        text = ""

    def fake_post(url, json, timeout):
        captured.update(url=url, payload=json, timeout=timeout)
        return Response()

    monkeypatch.setattr(output_module, "config", Config())
    monkeypatch.setattr(output_module.requests, "post", fake_post)
    assert output_class().send(fixture_notification(), target="truenas")
    assert payload_key in captured["payload"]
    assert "SYNTHETIC-TRUENAS" in json.dumps(captured["payload"])
    assert captured["timeout"] == 15


def test_router_uses_dedicated_truenas_targets(monkeypatch):
    calls = []

    class Config:
        def get(self, *keys, default=None):
            if keys == ("routing", "truenas"):
                return {
                    "outputs": [
                        {"output": "discord", "target": "truenas"},
                        {"output": "teams", "target": "truenas"},
                    ]
                }
            return default

    class Output:
        def __init__(self, name):
            self.name = name

        def send(self, notification, target):
            calls.append((self.name, notification.source, target))
            return True

    monkeypatch.setattr(router_module, "config", Config())
    router = Router()
    router.outputs = {"discord": Output("discord"), "teams": Output("teams")}
    assert router.route(fixture_notification())
    assert calls == [
        ("discord", "truenas", "truenas"),
        ("teams", "truenas", "truenas"),
    ]


def test_discord_aggregate_payload_limits_retain_essential_fields():
    alerts = [
        {
            "event_type": "new",
            "message": f"Synthetic alert {index} " + "x" * 1800,
            "status": "failure",
        }
        for index in range(50)
    ]
    notification = Notification(
        source="truenas",
        category="backup",
        status="failure",
        title="Synthetic oversized grouped alerts",
        body="Essential TrueNAS message " + "m" * 5000,
        items=alerts,
        metadata={
            "host": "SYNTHETIC-TRUENAS",
            "severity": "critical",
            "alert_count": 50,
            "alerts": alerts,
        },
    )
    formatter = TrueNASDiscordFormatter()
    embed = formatter.format(notification)["embeds"][0]
    assert formatter._embed_text_size(embed) <= formatter.EMBED_TEXT_BUDGET
    assert len(embed["fields"]) <= 25
    assert all(len(field["name"]) <= 256 for field in embed["fields"])
    assert all(len(field["value"]) <= 1024 for field in embed["fields"])
    serialized = json.dumps(embed)
    for essential in (
        "Essential TrueNAS message",
        "SYNTHETIC-TRUENAS",
        "backup",
        "Failure",
        "Critical",
        "50",
    ):
        assert essential in serialized
