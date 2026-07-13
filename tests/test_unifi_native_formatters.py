"""Dedicated UniFi Discord, Teams, output-selection, and routing tests."""

from __future__ import annotations

import json

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
    serialized = json.dumps(UniFiProtectDiscordFormatter().format(item))
    assert "SYNTHETIC-CAMERA" in serialized
    assert "configured_source_count" not in serialized
    assert "8" not in serialized


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
