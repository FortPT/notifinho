"""Dedicated UniFi Discord, Teams, output-selection, and routing tests."""

from __future__ import annotations

import json

from datetime import datetime, timezone

import pytest

import router as router_module

from formatters.discord_unifi import (
    UniFiDriveDiscordFormatter,
    UniFiNetworkDiscordFormatter,
    UniFiProtectDiscordFormatter,
)
from formatters.teams_unifi import (
    UniFiDriveTeamsFormatter,
    UniFiNetworkTeamsFormatter,
    UniFiProtectTeamsFormatter,
)
from formatters.unifi import format_protect_event_time, protect_device_display
from models import Notification
from outputs.discord import DiscordOutput
from outputs.teams import TeamsOutput
from router import Router


def notification(source: str) -> Notification:
    common = Notification(
        source=source,
        category="network" if source == "unifi_network" else "security",
        status="warning" if source == "unifi_drive" else "information",
        title="Synthetic UniFi event",
        body="Synthetic operational detail",
    )
    if source == "unifi_network":
        common.metadata = {
            "controller": "synthetic-controller.example.invalid",
            "severity": "information",
            "client_display_name": "SYNTHETIC-CLIENT",
            "client_alias": "SYNTHETIC-CLIENT",
            "client_hostname": "SYNTHETIC-CLIENT",
            "client_mac": "00:00:5e:00:53:30",
            "wifi_name": "SYNTHETIC-WIFI",
            "last_device_name": "SYNTHETIC-AP",
            "last_device_model": "Synthetic Model",
            "duration": "5m",
            "wifi_rssi": "-60 dBm",
        }
    elif source == "unifi_protect":
        common.metadata = {
            "trigger_key": "motion",
            "trigger_device": "SYNTHETIC-CAMERA",
            "event_time": "2026-01-02T03:04:05+00:00",
            "condition_source": "motion",
            "condition_operator": "is",
            "configured_source_count": 8,
            "event_link": "https://protect.example/event/synthetic",
        }
    else:
        common.category = "backup"
        common.metadata = {
            "system": "SYNTHETIC-DRIVE",
            "backup_task": "SYNTHETIC-BACKUP",
            "event_state": "partially completed",
            "action_link": "https://drive.example/manage/synthetic",
        }
    return common


@pytest.mark.parametrize(
    ("source", "discord_class", "teams_class"),
    [
        ("unifi_network", UniFiNetworkDiscordFormatter, UniFiNetworkTeamsFormatter),
        ("unifi_protect", UniFiProtectDiscordFormatter, UniFiProtectTeamsFormatter),
        ("unifi_drive", UniFiDriveDiscordFormatter, UniFiDriveTeamsFormatter),
    ],
)
def test_outputs_register_all_unifi_formatters_without_replacing_existing(
    source, discord_class, teams_class
):
    discord = DiscordOutput()
    teams = TeamsOutput()
    assert isinstance(discord.source_formatters[source], discord_class)
    assert isinstance(teams.source_formatters[source], teams_class)
    assert {"grafana", "qnap", "truenas", "zabbix"} <= set(discord.source_formatters)
    assert {"grafana", "qnap", "truenas", "zabbix"} <= set(teams.source_formatters)


@pytest.mark.parametrize(
    ("source", "discord_formatter", "teams_formatter", "expected"),
    [
        ("unifi_network", UniFiNetworkDiscordFormatter(), UniFiNetworkTeamsFormatter(), "SYNTHETIC-WIFI"),
        ("unifi_protect", UniFiProtectDiscordFormatter(), UniFiProtectTeamsFormatter(), "SYNTHETIC-CAMERA"),
        ("unifi_drive", UniFiDriveDiscordFormatter(), UniFiDriveTeamsFormatter(), "SYNTHETIC-BACKUP"),
    ],
)
def test_dedicated_discord_and_teams_cards(source, discord_formatter, teams_formatter, expected):
    item = notification(source)
    discord = discord_formatter.format(item)
    teams = teams_formatter.format(item)
    assert expected in json.dumps(discord)
    assert expected in json.dumps(teams)
    assert "Synthetic operational detail" in json.dumps(discord)
    assert "Synthetic operational detail" in json.dumps(teams)


def test_network_card_omits_mac_and_duplicate_hostname():
    item = notification("unifi_network")
    discord = json.dumps(UniFiNetworkDiscordFormatter().format(item))
    teams = json.dumps(UniFiNetworkTeamsFormatter().format(item))
    assert "00:00:5e:00:53:30" not in discord
    assert "00:00:5e:00:53:30" not in teams
    assert discord.count("SYNTHETIC-CLIENT") == 1
    assert teams.count("SYNTHETIC-CLIENT") == 1


def test_protect_card_does_not_list_configured_sources():
    item = notification("unifi_protect")
    payload = UniFiProtectDiscordFormatter().format(item)
    serialized = json.dumps(payload)
    assert "SYNTHETIC-CAMERA" in serialized
    assert "configured_source_count" not in serialized
    assert len(payload["embeds"][0]["fields"]) == 7


def _protect_field_names(item):
    discord = UniFiProtectDiscordFormatter().format(item)["embeds"][0]["fields"]
    teams = UniFiProtectTeamsFormatter().format(item)["attachments"][0]["content"]
    facts = _teams_facts(teams)
    return [field["name"] for field in discord], [fact["title"].rstrip(":") for fact in facts]


def _teams_facts(card):
    def visit(value):
        if isinstance(value, dict):
            if value.get("type") == "FactSet":
                return value.get("facts", [])
            for nested in value.values():
                found = visit(nested)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for nested in value:
                found = visit(nested)
                if found is not None:
                    return found
        return None

    return visit(card) or []


def test_protect_human_readable_camera_name_is_retained_on_both_platforms():
    item = notification("unifi_protect")
    item.metadata["trigger_device"] = "Front Door Camera"

    discord = json.dumps(
        UniFiProtectDiscordFormatter().format(item),
        ensure_ascii=False,
    )
    teams = json.dumps(
        UniFiProtectTeamsFormatter().format(item),
        ensure_ascii=False,
    )

    assert protect_device_display("Front Door Camera") == "Front Door Camera"
    assert "Front Door Camera" in discord
    assert "Front Door Camera" in teams


@pytest.mark.parametrize(
    "device_value",
    [
        "00:00:5e:00:53:41",
        "00-00-5e-00-53-41",
        "123e4567-e89b-42d3-a456-426614174000",
        "A1B2C3D4E5F60708",
        "FAKE_MAC",
    ],
)
def test_protect_private_or_opaque_device_is_omitted_without_empty_field(device_value):
    item = notification("unifi_protect")
    item.metadata["trigger_device"] = device_value

    discord = UniFiProtectDiscordFormatter().format(item)
    teams = UniFiProtectTeamsFormatter().format(item)
    discord_names, teams_names = _protect_field_names(item)

    assert protect_device_display(device_value) == ""
    assert device_value not in json.dumps(discord)
    assert device_value not in json.dumps(teams)
    assert "📷 Trigger device" not in discord_names
    assert "📷 Trigger device" not in teams_names
    assert item.metadata["trigger_device"] == device_value


@pytest.mark.parametrize(
    ("event_time", "expected"),
    [
        (datetime(2026, 7, 13, 1, 16, 35, 108000, tzinfo=timezone.utc).timestamp(), "13 Jul 2026 • 01:16"),
        (datetime(2026, 7, 13, 1, 16, 35, 108000, tzinfo=timezone.utc).timestamp() * 1000, "13 Jul 2026 • 01:16"),
        ("2026-07-13T01:16:35.108000+00:00", "13 Jul 2026 • 01:16"),
        ("2026-07-13T02:16:35.108000+01:00", "13 Jul 2026 • 02:16"),
    ],
)
def test_protect_event_time_formats_seconds_milliseconds_and_iso(event_time, expected):
    item = notification("unifi_protect")
    item.metadata["event_time"] = event_time

    discord = json.dumps(
        UniFiProtectDiscordFormatter().format(item),
        ensure_ascii=False,
    )
    teams = json.dumps(
        UniFiProtectTeamsFormatter().format(item),
        ensure_ascii=False,
    )

    assert format_protect_event_time(event_time) == expected
    assert expected in discord
    assert expected in teams
    assert ".108000" not in discord
    assert ".108000" not in teams


def test_protect_malformed_event_time_falls_back_safely():
    assert format_protect_event_time("synthetic-malformed-time") == "synthetic-malformed-time"


@pytest.mark.parametrize(
    ("source", "discord_formatter", "teams_formatter", "title_prefix"),
    [
        (
            "unifi_network",
            UniFiNetworkDiscordFormatter(),
            UniFiNetworkTeamsFormatter(),
            "📡 ℹ️",
        ),
        (
            "unifi_protect",
            UniFiProtectDiscordFormatter(),
            UniFiProtectTeamsFormatter(),
            "📹 ℹ️",
        ),
        (
            "unifi_drive",
            UniFiDriveDiscordFormatter(),
            UniFiDriveTeamsFormatter(),
            "💾 ⚠️",
        ),
    ],
)
def test_unifi_titles_have_one_application_and_status_icon(
    source, discord_formatter, teams_formatter, title_prefix
):
    item = notification(source)
    discord_title = discord_formatter.format(item)["embeds"][0]["title"]
    teams_title = teams_formatter.format(item)["attachments"][0]["content"]["body"][0]["text"]

    assert discord_title.startswith(f"{title_prefix} ")
    assert teams_title.startswith(f"{title_prefix} ")


@pytest.mark.parametrize(
    ("source", "discord_formatter", "teams_formatter", "expected_labels"),
    [
        (
            "unifi_network",
            UniFiNetworkDiscordFormatter(),
            UniFiNetworkTeamsFormatter(),
            {
                "🎛️ Controller",
                "🌐 Category",
                "ℹ️ Severity",
                "💻 Client",
                "📶 Network / Wi-Fi",
                "📍 Last device",
                "⏱️ Duration",
                "📡 Wireless",
            },
        ),
        (
            "unifi_protect",
            UniFiProtectDiscordFormatter(),
            UniFiProtectTeamsFormatter(),
            {
                "🎯 Trigger type",
                "📷 Trigger device",
                "🕒 Event time",
                "🔎 Condition",
            },
        ),
        (
            "unifi_drive",
            UniFiDriveDiscordFormatter(),
            UniFiDriveTeamsFormatter(),
            {"🖥️ System", "💾 Backup task", "🔄 Category"},
        ),
    ],
)
def test_unifi_discord_and_teams_labels_have_readable_icons(
    source, discord_formatter, teams_formatter, expected_labels
):
    item = notification(source)
    discord_fields = discord_formatter.format(item)["embeds"][0]["fields"]
    teams_card = teams_formatter.format(item)["attachments"][0]["content"]
    teams_text = json.dumps(teams_card, ensure_ascii=False)

    assert expected_labels <= {field["name"] for field in discord_fields}
    standard_metrics = {"Category", "Severity", "Event time", "State"}
    for label in expected_labels:
        plain_label = label.split(" ", 1)[-1]
        if plain_label in standard_metrics:
            if plain_label != "State":
                assert plain_label in teams_text
        else:
            assert label in teams_text
    assert all(any(character.isalpha() for character in label) for label in expected_labels)


@pytest.mark.parametrize("source", ["unifi_network", "unifi_protect", "unifi_drive"])
def test_unifi_teams_cards_do_not_repeat_icons_or_event_state(source):
    item = notification(source)
    card = UniFiNetworkTeamsFormatter().format(item) if source == "unifi_network" else (
        UniFiProtectTeamsFormatter().format(item)
        if source == "unifi_protect"
        else UniFiDriveTeamsFormatter().format(item)
    )
    rendered = json.dumps(card, ensure_ascii=False)
    facts = _teams_facts(card)

    assert "📌 📌" not in rendered
    assert all(fact["title"].count("📌") <= 1 for fact in facts)
    if source == "unifi_drive":
        assert not any(fact["title"].endswith(" State:") for fact in facts)


@pytest.mark.parametrize(
    ("status", "discord_color", "teams_color"),
    [
        ("failure", 0xE74C3C, "Attention"),
        ("warning", 0xF39C12, "Warning"),
        ("success", 0x2ECC71, "Good"),
        ("information", 0x3498DB, "Accent"),
    ],
)
def test_unifi_status_colors_are_unchanged(status, discord_color, teams_color):
    item = notification("unifi_network")
    item.status = status
    item.metadata["severity"] = status
    discord = UniFiNetworkDiscordFormatter().format(item)["embeds"][0]
    teams = UniFiNetworkTeamsFormatter().format(item)["attachments"][0]["content"]

    assert discord["color"] == discord_color
    assert teams["body"][0]["color"] == teams_color


def test_missing_values_do_not_leave_icon_only_fields():
    item = Notification(
        source="unifi_network",
        category="",
        status="information",
        title="Synthetic empty Network event",
        body="Synthetic detail",
        metadata={},
    )
    discord = UniFiNetworkDiscordFormatter().format(item)["embeds"][0]
    teams = UniFiNetworkTeamsFormatter().format(item)["attachments"][0]["content"]
    facts = _teams_facts(teams)

    assert [field["name"].split(" ", 1)[-1] for field in discord["fields"]] == [
        "Event", "Severity", "Category", "Event time",
    ]
    assert facts == []


def test_unifi_formatter_field_and_text_limits_remain_enforced():
    item = notification("unifi_network")
    item.title = "T" * 1000
    item.body = "B" * 5000
    item.metadata.update(
        controller="C" * 2000,
        client_display_name="D" * 2000,
        wifi_name="W" * 2000,
    )

    discord = UniFiNetworkDiscordFormatter().format(item)["embeds"][0]
    teams = UniFiNetworkTeamsFormatter().format(item)["attachments"][0]["content"]
    facts = _teams_facts(teams)

    assert len(discord["title"]) <= 256
    assert len(discord["description"]) <= 2048
    assert len(discord["fields"]) <= 25
    assert all(len(field["value"]) <= 1024 for field in discord["fields"])
    assert len(teams["body"][0]["text"]) <= 512
    assert len(teams["body"][2]["items"][0]["text"]) <= 4000
    assert all(len(fact["value"]) <= 1000 for fact in facts)


def test_partial_drive_cards_use_warning_style():
    item = notification("unifi_drive")
    discord = UniFiDriveDiscordFormatter().format(item)["embeds"][0]
    teams = UniFiDriveTeamsFormatter().format(item)["attachments"][0]["content"]
    assert discord["color"] == 0xF39C12
    assert teams["body"][0]["color"] == "Warning"


@pytest.mark.parametrize("source", ["unifi_network", "unifi_protect", "unifi_drive"])
def test_router_uses_independent_unifi_source_keys_and_shared_target(monkeypatch, source):
    calls = []

    class Config:
        def get(self, *keys, default=None):
            if keys == ("routing", source):
                return {"outputs": [{"output": "discord", "target": "unifi"}]}
            return default

    class Output:
        def send(self, item, target):
            calls.append((item.source, target))
            return True

    monkeypatch.setattr(router_module, "config", Config())
    router = Router()
    router.outputs = {"discord": Output()}

    assert router.route(notification(source))
    assert calls == [(source, "unifi")]
