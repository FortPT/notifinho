"""Regression tests for readable UniFi Protect notifications."""

from __future__ import annotations

import json

from formatters.discord_unifi import UniFiProtectDiscordFormatter
from formatters.teams_unifi import UniFiProtectTeamsFormatter
from parsers.unifi_protect import Parser as ProtectParser


def _admin_access_payload() -> dict:
    return {
        "alarm_id": "synthetic-admin-access-alarm",
        "timestamp": 1783948380,
        "alarm": {
            "name": "Notifinho - Protect - System",
            "conditions": [
                {
                    "condition": {
                        "source": "admin_access",
                        "type": "is",
                    }
                }
            ],
            "sources": [],
            "triggers": [
                {
                    "key": "admin_access",
                    "device": "nvr",
                    "timestamp": 1783948380,
                    "eventId": "synthetic-admin-access-event",
                }
            ],
        },
    }


def test_admin_access_parser_uses_the_event_as_the_visible_title():
    notification = ProtectParser().parse(
        _admin_access_payload(),
    )

    assert notification.title == "Admin Access"
    assert notification.subject == "Admin Access"
    assert notification.body == "Admin Access detected by NVR"
    assert notification.metadata["alarm_name"] == (
        "Notifinho - Protect - System"
    )
    assert notification.metadata["trigger_key"] == "admin_access"
    assert notification.metadata["trigger_label"] == "Admin Access"
    assert notification.metadata["condition_operator"] == "is"


def test_admin_access_cards_keep_the_rule_and_remove_raw_condition_text():
    notification = ProtectParser().parse(
        _admin_access_payload(),
    )

    discord = UniFiProtectDiscordFormatter().format(
        notification,
    )
    teams = UniFiProtectTeamsFormatter().format(
        notification,
    )

    serialized = json.dumps(
        {
            "discord": discord,
            "teams": teams,
        },
        ensure_ascii=False,
    )

    assert "📹 ℹ️ Admin Access" in serialized
    assert "Admin Access detected by NVR" in serialized
    assert "🎯 Trigger type" in serialized
    assert "🚨 Alarm rule" in serialized
    assert "Notifinho - Protect - System" in serialized
    assert "admin_access" not in serialized
    assert "Admin_Access" not in serialized
    assert "admin access is" not in serialized.casefold()
    assert "🔎 Condition" not in serialized
