"""Synthetic contract tests for Synology DSM notification support."""

from __future__ import annotations

import copy
import http.client
import json
import threading

from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path
from urllib.parse import urlencode

import pytest

import router as router_module

from dispatcher import Dispatcher
from formatters.discord_synology import SynologyDiscordFormatter
from formatters.teams_synology import SynologyTeamsFormatter
from inputs.http import HTTPServer
from outputs.discord import DiscordOutput
from outputs.teams import TeamsOutput
from parsers.synology import Parser
from router import Router


FIXTURES = Path(__file__).parent / "fixtures" / "synology"


def webhook_fixture() -> dict:
    return json.loads(
        (FIXTURES / "backup_failure.json").read_text(encoding="utf-8")
    )


def email_fixture():
    with (FIXTURES / "storage_degraded.eml").open("rb") as stream:
        return BytesParser(policy=policy.default).parse(stream)


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


def request(port, target, body, content_type="application/json", token=""):
    headers = {"Content-Type": content_type}
    if token:
        headers["X-Notifinho-Token"] = token
    if isinstance(body, dict):
        body = json.dumps(body).encode("utf-8")
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    connection.request("POST", target, body=body, headers=headers)
    response = connection.getresponse()
    status = response.status
    response.read()
    connection.close()
    return status


def test_synthetic_storage_email_is_normalized_without_raw_dump():
    item = Parser().parse(email_fixture())

    assert item.source == "synology"
    assert item.category == "storage"
    assert item.status == "warning"
    assert item.title == "Storage Pool 1 on synthetic-dsm-01 is degraded"
    assert item.body == "Storage Pool 1 has degraded and requires attention."
    assert item.start_time == "2026-07-15T12:30:00Z"
    assert item.metadata["nas_name"] == "synthetic-dsm-01"
    assert item.metadata["model"] == "DS-SYNTHETIC"
    assert item.metadata["storage_pool"] == "Storage Pool 1"
    assert item.metadata["volume"] == "Volume 1"
    assert item.metadata["validation"] == "synthetic-fixture"
    assert "Dear user" not in item.body
    assert "Sincerely" not in item.body


def test_dispatcher_detects_synology_branded_email():
    assert Dispatcher().parse(email_fixture()).source == "synology"


def test_unbranded_notification_is_not_stolen():
    message = EmailMessage()
    message["From"] = "Monitoring <alerts@example.invalid>"
    message["Subject"] = "Storage notification"
    message.set_content("Volume warning")

    assert Dispatcher().parse(message).source == "generic"


def test_webhook_contract_is_normalized():
    item = Parser().parse_webhook(webhook_fixture())

    assert item.source == "synology"
    assert item.category == "backup"
    assert item.status == "failure"
    assert item.title == "Synthetic Hyper Backup failure"
    assert item.start_time == "2026-07-15T12:45:00Z"
    assert item.metadata["nas_name"] == "synthetic-dsm-01"
    assert item.metadata["task"] == "Synthetic Nightly Backup"
    assert item.metadata["storage"] == "synthetic-backup-vault"
    assert item.metadata["parser_confidence"] == "high"


def test_recovery_webhook_maps_to_success_and_end_time():
    payload = webhook_fixture()
    payload.update(
        severity="success",
        status="resolved",
        message="Synthetic backup destination recovered.",
    )
    item = Parser().parse_webhook(payload)

    assert item.status == "success"
    assert item.end_time == "2026-07-15T12:45:00Z"
    assert item.metadata["state"] == "resolved"


@pytest.mark.parametrize(
    "mutation",
    (
        lambda value: value.pop("schema"),
        lambda value: value.update(schema="unknown"),
        lambda value: value.update(source="other"),
        lambda value: value.update(severity="emergency"),
        lambda value: value.update(metadata=[]),
        lambda value: value.update(nas_name=[]),
        lambda value: value.update(title="", message=""),
    ),
)
def test_invalid_or_unbranded_webhooks_are_rejected(mutation):
    payload = copy.deepcopy(webhook_fixture())
    mutation(payload)
    assert Parser.is_envelope(payload) is False
    assert Dispatcher().parse_webhook("synology", payload) is None


def test_json_endpoint_accepts_header_and_query_authentication():
    token = "synthetic-synology-secret"
    with RunningServer(shared_secret=token) as running:
        missing = request(
            running.port,
            "/synology/events",
            webhook_fixture(),
        )
        query = request(
            running.port,
            f"/synology/events?token={token}",
            webhook_fixture(),
        )
        header = request(
            running.port,
            "/synology/events",
            webhook_fixture(),
            token=token,
        )

    assert (missing, query, header) == (401, 204, 204)
    assert [item.source for item in running.router.notifications] == [
        "synology",
        "synology",
    ]


def test_form_encoded_contract_is_accepted_for_custom_provider():
    payload = webhook_fixture()
    flat = {
        key: value
        for key, value in payload.items()
        if key != "metadata"
    }
    flat.update(payload["metadata"])
    body = urlencode(flat).encode("utf-8")

    with RunningServer(shared_secret="synthetic-secret") as running:
        status = request(
            running.port,
            "/synology/events",
            body,
            content_type="application/x-www-form-urlencoded",
            token="synthetic-secret",
        )

    assert status == 204
    assert running.router.notifications[0].metadata["nas_name"] == (
        "synthetic-dsm-01"
    )


def test_form_encoded_duplicate_fields_are_rejected():
    body = (
        "schema=notifinho.synology.v1&schema=duplicate&source=synology-dsm"
        "&title=test&severity=info"
    ).encode("utf-8")
    with RunningServer() as running:
        status = request(
            running.port,
            "/synology/events",
            body,
            content_type="application/x-www-form-urlencoded",
        )
    assert status == 400


def test_dedicated_formatters_are_registered_and_bounded():
    item = Parser().parse_webhook(webhook_fixture())
    item.title = "T" * 800
    item.body = "B" * 8000
    discord = SynologyDiscordFormatter().format(item)["embeds"][0]
    teams = SynologyTeamsFormatter().format(item)["attachments"][0]["content"]

    assert isinstance(
        DiscordOutput().source_formatters["synology"],
        SynologyDiscordFormatter,
    )
    assert isinstance(
        TeamsOutput().source_formatters["synology"],
        SynologyTeamsFormatter,
    )
    assert len(discord["title"]) <= 256
    assert len(discord["fields"][0]["value"]) <= 1024
    assert len(teams["body"][0]["text"]) <= 512
    assert len(teams["body"][2]["items"][0]["text"]) <= 4000


def test_router_uses_synology_source_key(monkeypatch):
    calls = []

    class Config:
        def get(self, *keys, default=None):
            if keys == ("routing", "synology"):
                return {"outputs": [{"output": "discord", "target": "synology"}]}
            return default

    class Output:
        def send(self, item, target):
            calls.append((item.source, target))
            return True

    monkeypatch.setattr(router_module, "config", Config())
    router = Router()
    router.outputs = {"discord": Output()}

    assert router.route(Parser().parse_webhook(webhook_fixture())) is True
    assert calls == [("synology", "synology")]


def test_cards_hide_extra_metadata_and_source_fields():
    item = Parser().parse_webhook(webhook_fixture())
    item.metadata["metadata"]["serial"] = "SYNTHETIC-SERIAL-HIDDEN"
    rendered = json.dumps(
        {
            "discord": SynologyDiscordFormatter().format(item),
            "teams": SynologyTeamsFormatter().format(item),
        }
    )

    assert "synthetic-dsm-01" in rendered
    assert "Synthetic Nightly Backup" in rendered
    assert "SYNTHETIC-SERIAL-HIDDEN" not in rendered
