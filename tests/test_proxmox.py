"""Synthetic contract tests for Proxmox VE notification support."""

from __future__ import annotations

import copy
import http.client
import json
import threading

from email import policy
from email.parser import BytesParser
from pathlib import Path

import pytest

import router as router_module

from dispatcher import Dispatcher
from formatters.discord_proxmox import ProxmoxDiscordFormatter
from formatters.teams_proxmox import ProxmoxTeamsFormatter
from inputs.http import HTTPServer
from outputs.discord import DiscordOutput
from outputs.teams import TeamsOutput
from parsers.proxmox import Parser
from router import Router


FIXTURES = Path(__file__).parent / "fixtures" / "proxmox"


def webhook_fixture() -> dict:
    return json.loads((FIXTURES / "event_warning.json").read_text(encoding="utf-8"))


def email_fixture():
    with (FIXTURES / "backup_failure.eml").open("rb") as stream:
        return BytesParser(policy=policy.default).parse(stream)


class RecordingRouter:
    def __init__(self):
        self.notifications = []

    def route(self, notification):
        self.notifications.append(notification)
        return True


def request(server, path, payload, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
    connection.request(
        "POST",
        path,
        body=json.dumps(payload).encode("utf-8"),
        headers=headers or {"Content-Type": "application/json"},
    )
    response = connection.getresponse()
    status = response.status
    response.read()
    connection.close()
    return status


def test_synthetic_backup_email_is_normalized():
    item = Parser().parse(email_fixture())

    assert item.source == "proxmox"
    assert item.category == "backup"
    assert item.status == "failure"
    assert item.metadata["node"] == "synthetic-pve-01"
    assert item.metadata["storage"] == "synthetic-backup-store"
    assert item.start_time == "2026-07-15T00:45:00Z"
    assert item.duration == "00:15:00"
    assert item.vm_total == 2
    assert item.vm_success == 1
    assert item.vm_failed == 1
    assert item.successful_vms == ["100 | home-assistant"]
    assert item.failed_vms == ["101 | synthetic-db"]
    assert item.body == "Backup completed with errors: 1 guest failed out of 2 guests."
    assert item.metadata["validation"] == "synthetic-fixture"


def test_dispatcher_detects_characteristic_vzdump_subject():
    item = Dispatcher().parse(email_fixture())
    assert item.source == "proxmox"


def test_webhook_contract_is_normalized():
    item = Parser().parse_webhook(webhook_fixture())

    assert item.source == "proxmox"
    assert item.category == "storage"
    assert item.status == "warning"
    assert item.title == "Synthetic storage warning"
    assert item.start_time == "2026-07-15T01:15:00Z"
    assert item.metadata["node"] == "synthetic-pve-01"
    assert item.metadata["storage"] == "synthetic-backup-store"
    assert item.metadata["metadata"]["usage_percent"] == "85"
    assert item.metadata["parser_confidence"] == "high"


@pytest.mark.parametrize(
    "mutation",
    (
        lambda value: value.pop("schema"),
        lambda value: value.update(schema="unknown"),
        lambda value: value.update(source="other"),
        lambda value: value.update(severity="emergency"),
        lambda value: value.update(metadata=[]),
        lambda value: value.update(title="", message=""),
    ),
)
def test_invalid_or_unbranded_webhooks_are_rejected(mutation):
    payload = copy.deepcopy(webhook_fixture())
    mutation(payload)
    assert Parser.is_envelope(payload) is False
    assert Dispatcher().parse_webhook("proxmox", payload) is None


def test_http_endpoint_requires_header_token_and_routes():
    router = RecordingRouter()
    server = HTTPServer(
        ("127.0.0.1", 0),
        Dispatcher(),
        router,
        1_048_576,
        "synthetic-secret",
    )
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        missing = request(server, "/proxmox/events", webhook_fixture())
        success = request(
            server,
            "/proxmox/events",
            webhook_fixture(),
            {
                "Content-Type": "application/json",
                "X-Notifinho-Token": "synthetic-secret",
            },
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert (missing, success) == (401, 204)
    assert [item.source for item in router.notifications] == ["proxmox"]


def test_dedicated_formatters_are_registered_and_bounded():
    item = Parser().parse_webhook(webhook_fixture())
    item.title = "T" * 800
    item.body = "B" * 8000
    discord = ProxmoxDiscordFormatter().format(item)["embeds"][0]
    teams = ProxmoxTeamsFormatter().format(item)["attachments"][0]["content"]

    assert isinstance(DiscordOutput().source_formatters["proxmox"], ProxmoxDiscordFormatter)
    assert isinstance(TeamsOutput().source_formatters["proxmox"], ProxmoxTeamsFormatter)
    assert len(discord["title"]) <= 256
    assert len(discord["fields"][0]["value"]) <= 1024
    assert len(teams["body"][0]["text"]) <= 512
    assert len(teams["body"][2]["items"][0]["text"]) <= 4000


def test_router_uses_proxmox_source_key(monkeypatch):
    calls = []

    class Config:
        def get(self, *keys, default=None):
            if keys == ("routing", "proxmox"):
                return {"outputs": [{"output": "discord", "target": "proxmox"}]}
            return default

    class Output:
        def send(self, item, target):
            calls.append((item.source, target))
            return True

    monkeypatch.setattr(router_module, "config", Config())
    router = Router()
    router.outputs = {"discord": Output()}

    assert router.route(Parser().parse_webhook(webhook_fixture())) is True
    assert calls == [("proxmox", "proxmox")]


def test_formatter_does_not_render_extra_template_metadata():
    item = Parser().parse_webhook(webhook_fixture())
    rendered = json.dumps(
        {
            "discord": ProxmoxDiscordFormatter().format(item),
            "teams": ProxmoxTeamsFormatter().format(item),
        }
    )
    assert "synthetic-pve-01" in rendered
    assert "synthetic-backup-store" in rendered
    assert "usage_percent" not in rendered


def test_backup_card_uses_summary_instead_of_raw_email_dump():
    item = Parser().parse(email_fixture())
    rendered = json.dumps(
        {
            "discord": ProxmoxDiscordFormatter().format(item),
            "teams": ProxmoxTeamsFormatter().format(item),
        }
    )

    assert "Backup completed with errors" in rendered
    assert "101 | synthetic-db" in rendered
    assert "synthetic timeout" in rendered
    assert "100 | home-assistant" in rendered
    assert "VMID NAME STATUS TIME SIZE MESSAGE" not in rendered
    assert "TASK ERROR: job errors" not in rendered
