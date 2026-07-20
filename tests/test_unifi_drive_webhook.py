# Native UniFi Drive Alarm Manager webhook regression tests.

from __future__ import annotations

import http.client
import json
import threading

from pathlib import Path

import pytest

from dispatcher import Dispatcher
from formatters.discord_unifi import UniFiDriveDiscordFormatter
from formatters.teams_unifi import UniFiDriveTeamsFormatter
from inputs.http import HTTPServer
from parsers.unifi_drive import Parser as DriveParser


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "unifi"
    / "drive"
    / "settings_alarm.json"
)


def _teams_facts(value):
    if isinstance(value, dict):
        if value.get("type") == "FactSet":
            return value.get("facts", [])
        for nested in value.values():
            facts = _teams_facts(nested)
            if facts:
                return facts
    elif isinstance(value, list):
        for nested in value:
            facts = _teams_facts(nested)
            if facts:
                return facts
    return []


def drive_payload() -> dict:
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
        self.thread = threading.Thread(
            target=self.server.serve_forever,
        )

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


def request(port, body, headers=None):
    connection = http.client.HTTPConnection(
        "127.0.0.1",
        port,
        timeout=2,
    )
    connection.request(
        "POST",
        "/unifi/drive",
        body=body,
        headers=headers or {},
    )
    response = connection.getresponse()
    status = response.status
    response.read()
    connection.close()
    return status


def test_drive_webhook_normalizes_discovered_default_content():
    payload = drive_payload()

    notification = DriveParser().parse_webhook(payload)

    assert notification.source == "unifi_drive"
    assert notification.title == "Settings"
    assert notification.subject == "Settings"
    assert notification.body == "Settings alarm triggered"
    assert notification.status == "information"
    assert notification.category == "administration"
    assert notification.metadata["event_title"] == "Settings"
    assert notification.metadata["alarm_name"] == "Notifinho | Drive - Settings"
    assert notification.metadata["event_state"] == "triggered"
    assert notification.metadata["format"] == "webhook"
    assert notification.metadata["alarm_id"] == payload["alarm_id"]


def test_drive_webhook_preserves_an_unstructured_alarm_name():
    payload = {
        "alarm_id": "00000000-0000-4000-8000-000000000002",
        "text": 'Alarm "Storage pool warning" was triggered',
    }

    notification = DriveParser().parse_webhook(payload)

    assert notification.title == "Storage pool warning"
    assert notification.body == "Storage pool warning alarm triggered"
    assert notification.metadata["alarm_name"] == "Storage pool warning"


def test_drive_webhook_dispatcher_selects_drive_parser():
    notification = Dispatcher().parse_webhook(
        "drive",
        drive_payload(),
    )

    assert notification is not None
    assert notification.source == "unifi_drive"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"alarm_id": "synthetic", "text": "ordinary JSON"},
        {
            "alarm_id": "",
            "text": 'Alarm "Synthetic" was triggered',
        },
        {
            "alarm_id": "synthetic",
            "text": 123,
        },
    ],
)
def test_drive_webhook_rejects_false_positive_json(payload):
    assert DriveParser.is_envelope(payload) is False
    assert Dispatcher().parse_webhook("drive", payload) is None


def test_drive_http_endpoint_uses_global_shared_token_and_routes():
    body = json.dumps(drive_payload()).encode("utf-8")
    token = "synthetic-shared-secret"

    with RunningServer(shared_secret=token) as running:
        missing = request(
            running.port,
            body,
            {"Content-Type": "application/json"},
        )
        success = request(
            running.port,
            body,
            {
                "Content-Type": "application/json",
                "X-Notifinho-Token": token,
            },
        )

    assert (missing, success) == (401, 204)
    assert [
        notification.source
        for notification in running.router.notifications
    ] == ["unifi_drive"]


def test_drive_alarm_rule_is_formatted_and_alarm_id_is_hidden():
    payload = drive_payload()
    notification = DriveParser().parse_webhook(payload)

    discord = UniFiDriveDiscordFormatter().format(notification)
    teams = UniFiDriveTeamsFormatter().format(notification)
    rendered = json.dumps({"discord": discord, "teams": teams})

    discord_embed = discord["embeds"][0]
    discord_details = next(
        field
        for field in discord_embed["fields"]
        if field["name"] == "📋 Event details"
    )

    teams_card = teams["attachments"][0]["content"]
    teams_alarm_rule = next(
        fact
        for fact in _teams_facts(teams_card)
        if fact["title"] == "🚨 Alarm rule:"
    )

    assert payload["alarm_id"] not in rendered

    assert discord_embed["title"].endswith("Settings")
    assert discord_embed["description"].endswith(
        "UniFi Drive • ℹ️ **Triggered** • 📍 Administration"
    )
    assert "🚨 **Alarm rule:** Notifinho | Drive - Settings" in (
        discord_details["value"]
    )
    assert discord_details["inline"] is False

    assert teams_card["body"][0]["text"].endswith("Settings")
    assert teams_card["body"][2]["items"][0]["text"] == "🔔 Settings alarm triggered"
    assert teams_alarm_rule == {
        "title": "🚨 Alarm rule:",
        "value": "Notifinho | Drive - Settings",
    }
