"""Grafana Discord, Teams, and output-selection tests."""

from __future__ import annotations

import json

from email import policy
from email.parser import BytesParser
from pathlib import Path

import pytest

import outputs.discord as discord_output_module
import outputs.teams as teams_output_module

from formatters.discord_grafana import GrafanaDiscordFormatter
from formatters.teams_grafana import GrafanaTeamsFormatter
from models import Notification
from outputs.discord import DiscordOutput
from outputs.teams import TeamsOutput
from parsers.grafana import Parser as GrafanaParser
from version import VERSION


FIXTURES = Path(__file__).parent / "fixtures" / "grafana"


def fixture_notification(name: str):

    with (FIXTURES / name).open("rb") as fixture:

        message = BytesParser(
            policy=policy.default,
        ).parse(fixture)

    return GrafanaParser().parse(message)


def test_firing_payloads_contain_operational_details():

    notification = fixture_notification("alert_firing.eml")

    discord = GrafanaDiscordFormatter().format(notification)
    teams = GrafanaTeamsFormatter().format(notification)

    embed = discord["embeds"][0]
    card = teams["attachments"][0]["content"]

    assert embed["color"] == 0xE74C3C
    assert embed["footer"]["text"].endswith(f"Notifinho v{VERSION}")
    assert card["body"][0]["color"] == "Attention"

    for expected in (
        "Synthetic API Latency",
        "Synthetic API Latency Rule",
        "Synthetic Platform",
        "Synthetic Service Overview",
        "Synthetic Latency Panel",
        "Synthetic Metrics Source",
        "service=synthetic-api",
        "A=2.75",
        "grafana.synthetic.invalid",
    ):

        assert expected in json.dumps(discord)
        assert expected in json.dumps(teams)


@pytest.mark.parametrize(
    (
        "status",
        "state",
        "severity",
        "discord_color",
        "teams_color",
    ),
    [
        ("failure", "Firing", "Critical", 0xE74C3C, "Attention"),
        ("failure", "Error", "Error", 0xE74C3C, "Attention"),
        ("warning", "Warning", "Warning", 0xF39C12, "Warning"),
        ("warning", "Pending", "Warning", 0xF39C12, "Warning"),
        ("warning", "No Data", "Warning", 0xF39C12, "Warning"),
        ("success", "Resolved", "Normal", 0x2ECC71, "Good"),
        ("success", "Normal", "Normal", 0x2ECC71, "Good"),
        ("information", "Test", "Information", 0x3498DB, "Accent"),
    ],
)
def test_status_colors_are_aligned(
    status: str,
    state: str,
    severity: str,
    discord_color: int,
    teams_color: str,
):

    notification = Notification(
        source="grafana",
        category="alerting",
        status=status,
        metadata={
            "alert_name": "Synthetic Status Alert",
            "state": state,
            "severity": severity,
            "message": "Synthetic status event",
        },
    )

    embed = GrafanaDiscordFormatter().format(notification)["embeds"][0]
    card = GrafanaTeamsFormatter().format(notification)["attachments"][0][
        "content"
    ]

    assert embed["color"] == discord_color
    assert card["body"][0]["color"] == teams_color


@pytest.mark.parametrize(
    (
        "fixture_name",
        "expected_values",
    ),
    [
        (
            "alert_resolved.eml",
            ("Resolved", "Synthetic API latency returned to normal"),
        ),
        (
            "alert_pending.eml",
            ("Pending", "Synthetic Queue Dashboard", "A=82"),
        ),
        (
            "alert_no_data.eml",
            ("No Data", "Synthetic Metrics Source"),
        ),
        (
            "datasource_error.eml",
            ("Error", "Synthetic Query Source", "Evaluation Error"),
        ),
        (
            "test_notification.eml",
            ("Test", "Synthetic Contact Point Test"),
        ),
    ],
)
def test_event_specific_details_appear_in_both_outputs(
    fixture_name: str,
    expected_values: tuple[str, ...],
):

    notification = fixture_notification(fixture_name)

    discord = json.dumps(
        GrafanaDiscordFormatter().format(notification)
    )
    teams = json.dumps(
        GrafanaTeamsFormatter().format(notification)
    )

    for expected in expected_values:

        assert expected in discord
        assert expected in teams


def test_missing_and_malformed_optional_metadata_is_omitted():

    notification = Notification(
        source="grafana",
        status="information",
        metadata={
            "alert_name": "Synthetic Sparse Alert",
            "message": "Synthetic sparse event",
            "state": "Information",
            "severity": "",
            "dashboard": None,
            "datasource": "",
            "event_time": None,
            "source_fields": "malformed",
        },
    )

    embed = GrafanaDiscordFormatter().format(notification)["embeds"][0]
    card = GrafanaTeamsFormatter().format(notification)["attachments"][0][
        "content"
    ]

    assert all(
        field["name"] and field["value"]
        for field in embed["fields"]
    )

    serialized_discord = json.dumps(embed)
    serialized_teams = json.dumps(card)

    assert "Datasource" not in serialized_discord
    assert "Event time" not in serialized_discord
    assert "Datasource" not in serialized_teams
    assert "Event time" not in serialized_teams

    for item in _walk(card):

        if item.get("type") == "TextBlock":

            assert str(item.get("text", "")).strip()

        if item.get("type") == "FactSet":

            assert all(
                fact.get("title") and fact.get("value")
                for fact in item.get("facts", [])
            )


def test_discord_embed_budget_with_oversized_unknown_metadata():

    notification = Notification(
        source="grafana",
        category="alerting",
        status="failure",
        metadata={
            "alert_name": "Synthetic Oversized Alert",
            "state": "Firing",
            "severity": "Critical",
            "message": "Essential Grafana event " + "m" * 1800,
            "alert_rule": "Synthetic Essential Rule",
            "folder": "Synthetic Essential Folder",
            "dashboard": "Synthetic Essential Dashboard",
            "event_time": "2026-07-12 12:00:00",
            "source_fields": {
                f"Unknown Grafana Field {index}": "x" * 2000
                for index in range(50)
            },
        },
    )

    formatter = GrafanaDiscordFormatter()
    embed = formatter.format(notification)["embeds"][0]

    assert formatter._embed_text_size(embed) <= 5900
    assert len(embed["fields"]) <= 25
    assert len(embed["title"]) <= 256
    assert len(embed["description"]) <= 4096
    assert all(
        len(field["name"]) <= 256
        and len(field["value"]) <= 1024
        for field in embed["fields"]
    )

    serialized = json.dumps(embed)

    assert "Essential Grafana event" in serialized
    assert "Critical" in serialized
    assert "Synthetic Essential Rule" in serialized
    assert any(
        field["value"].endswith("…")
        for field in embed["fields"]
    )


def test_outputs_register_grafana_without_replacing_existing_formatters():

    discord = DiscordOutput()
    teams = TeamsOutput()

    assert isinstance(
        discord.source_formatters["grafana"],
        GrafanaDiscordFormatter,
    )
    assert isinstance(
        teams.source_formatters["grafana"],
        GrafanaTeamsFormatter,
    )
    assert "qnap" in discord.source_formatters
    assert "qnap" in teams.source_formatters
    assert "zabbix" in discord.source_formatters
    assert "zabbix" in teams.source_formatters


@pytest.mark.parametrize(
    (
        "output_class",
        "output_module",
        "payload_key",
    ),
    [
        (DiscordOutput, discord_output_module, "components"),
        (TeamsOutput, teams_output_module, "attachments"),
    ],
)
def test_actual_output_selects_grafana_formatter_without_network(
    monkeypatch,
    output_class,
    output_module,
    payload_key: str,
):

    captured = {}

    class Config:

        def get(self, *keys, default=None):

            if keys[-1:] == ("webhook",):

                return "https://example.invalid/webhook/synthetic/id"

            return default

    class Response:

        status_code = 204
        text = ""

    def fake_post(url, json, timeout):

        captured["url"] = url
        captured["payload"] = json
        captured["timeout"] = timeout

        return Response()

    monkeypatch.setattr(output_module, "config", Config())
    monkeypatch.setattr(output_module.requests, "post", fake_post)

    assert output_class().send(
        fixture_notification("alert_firing.eml"),
        target="grafana",
    )

    assert payload_key in captured["payload"]
    assert "Synthetic API Latency" in json.dumps(captured["payload"])
    assert captured["timeout"] == 15


def _walk(value):

    if isinstance(value, dict):

        yield value

        for nested in value.values():

            yield from _walk(nested)

    elif isinstance(value, list):

        for nested in value:

            yield from _walk(nested)
