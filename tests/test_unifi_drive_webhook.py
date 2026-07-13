# Native UniFi Drive Alarm Manager webhook regression tests.

from __future__ import annotations

import http.client
import json
import threading

from pathlib import Path

import pytest

from dispatcher import Dispatcher
from formatters.discord_unifi import UniFiDriveDiscordFormatter
from inputs.http import HTTPServer
from parsers.unifi_drive import Parser as DriveParser


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "unifi"
    / "drive"
    / "settings_alarm.json"
)


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
    assert notification.title == "Notifinho | Drive - Settings"
    assert notification.body == payload["text"]
    assert notification.status == "information"
    assert notification.category == "administration"
    assert notification.metadata["event_state"] == "triggered"
    assert notification.metadata["format"] == "webhook"
    assert notification.metadata["alarm_id"] == payload["alarm_id"]


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


def test_drive_alarm_id_is_not_visible_in_discord_card():
    payload = drive_payload()
    notification = DriveParser().parse_webhook(payload)

    rendered = json.dumps(
        UniFiDriveDiscordFormatter().format(notification),
    )

    assert payload["alarm_id"] not in rendered
    assert "Notifinho | Drive - Settings" in rendered
    assert "triggered" in rendered
