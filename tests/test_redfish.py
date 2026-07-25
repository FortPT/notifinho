"""Synthetic candidate tests for shared Redfish and hardware adapters."""

from __future__ import annotations

import http.client
import json
import threading

from email import policy
from email.parser import BytesParser
from pathlib import Path

import pytest

from config import config
from dispatcher import Dispatcher
from formatters.discord_hardware import (
    DellIDRACDiscordFormatter,
    HPEILODiscordFormatter,
    SupermicroDiscordFormatter,
)
from formatters.teams_hardware import (
    DellIDRACTeamsFormatter,
    HPEILOTeamsFormatter,
    SupermicroTeamsFormatter,
)
from inputs.http import HTTPServer
from models import Notification
from outputs.discord import DiscordOutput
from outputs.teams import TeamsOutput
from parsers.redfish import RedfishParser
from router import Router as DeliveryRouter


FIXTURES = Path(__file__).parent / "fixtures" / "redfish"


def payload(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def email(name: str):
    with (FIXTURES / name).open("rb") as stream:
        return BytesParser(policy=policy.default).parse(stream)


class RecordingRouter:
    def __init__(self):
        self.notifications = []

    def route(self, notification):
        self.notifications.append(notification)
        return True


class RunningServer:
    def __init__(self, secret="synthetic-redfish-secret"):
        self.router = RecordingRouter()
        self.server = HTTPServer(
            ("127.0.0.1", 0),
            Dispatcher(),
            self.router,
            1_048_576,
            secret,
        )
        self.thread = threading.Thread(target=self.server.serve_forever)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


def post(port: int, path: str, value: dict, token: str = "") -> int:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Notifinho-Token"] = token
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    connection.request("POST", path, json.dumps(value), headers)
    response = connection.getresponse()
    status = response.status
    response.read()
    connection.close()
    return status


@pytest.mark.parametrize(
    ("fixture", "hint", "source", "category", "status"),
    (
        ("supermicro_thermal.json", "supermicro", "supermicro", "thermal", "failure"),
        ("hpe_memory.json", "hpe", "hpe_ilo", "memory", "warning"),
        ("dell_storage.json", "dell", "dell_idrac", "storage", "failure"),
    ),
)
def test_redfish_vendor_candidates_are_normalized(fixture, hint, source, category, status):
    item = RedfishParser().parse(payload(fixture), hint)[0]

    assert item.source == source
    assert item.category == category
    assert item.status == status
    assert item.start_time.startswith("2026-07-15T20:")
    assert len(item.metadata["deduplication_key"]) == 64
    assert item.metadata["origin"].startswith("/redfish/v1/")
    assert "synthetic" not in json.dumps(item.metadata).casefold() or item.metadata["event_id"]


def test_generic_redfish_endpoint_detects_vendor_from_standard_fields():
    item = Dispatcher().parse_webhook("redfish", payload("hpe_memory.json"))[0]
    assert item.source == "hpe_ilo"
    assert item.metadata["provider"] == "HPE iLO"


def test_redfish_context_is_presented_as_host_and_scopes_deduplication():
    srv_01_payload = payload("supermicro_thermal.json")
    srv_02_payload = json.loads(json.dumps(srv_01_payload))
    srv_02_payload["Context"] = "SRV-02"
    srv_02_payload["Events"][0].pop("Resolution", None)
    srv_02_payload["Events"][0]["MessageArgs"] = [""]

    srv_01 = RedfishParser().parse(srv_01_payload, "supermicro")[0]
    srv_02 = RedfishParser().parse(srv_02_payload, "supermicro")[0]
    discord = SupermicroDiscordFormatter().format(srv_01)
    teams = SupermicroTeamsFormatter().format(srv_01)
    rendered = json.dumps({"discord": discord, "teams": teams})

    assert srv_01.metadata["system"] == "SRV-01"
    assert srv_02.metadata["system"] == "SRV-02"
    assert srv_02.metadata["recommended_action"] == ""
    assert srv_01.metadata["deduplication_key"] != srv_02.metadata["deduplication_key"]
    assert "SRV-01" in rendered
    assert "SRV-01 \\u2022 CPU 1 temperature exceeded" in rendered
    assert "Recommended action" not in json.dumps(
        SupermicroTeamsFormatter().format(srv_02)
    )


def test_dell_ipmi_session_event_extracts_source_ip():
    value = payload("dell_storage.json")
    value["Events"][0].update({
        "MessageId": "USR0030",
        "Message": (
            "Successfully logged in using root, from 192.168.0.164 "
            "and IPMI over LAN."
        ),
    })

    item = RedfishParser().parse(value, "dell")[0]

    assert item.metadata["source_ip"] == "192.168.0.164"
    assert "🌐 **Source IP:** 192.168.0.164" in json.dumps(
        DellIDRACDiscordFormatter().format(item),
        ensure_ascii=False,
    )


def test_dell_legacy_context_and_audit_title_are_readable():
    value = payload("dell_storage.json")
    value["Context"] = "NotifinhoAlfaCompat"
    value["Events"][0].update({
        "MessageId": "USR0030",
        "Message": (
            "Successfully logged in using root, from 192.168.0.251 "
            "and REDFISH."
        ),
    })

    item = RedfishParser().parse(value, "dell")[0]

    assert item.metadata["system"] == "ALFA"
    assert item.title == "User Login"
    assert item.body.startswith("Successfully logged in")


@pytest.mark.parametrize(
    ("message_id", "transport"),
    [
        ("USR0030", "IPMI over LAN"),
        ("USR0030", "REDFISH"),
        ("USR0032", "IPMI over LAN"),
        ("USR0032", "REDFISH"),
    ],
)
def test_trusted_dell_session_audit_is_suppressed(
    monkeypatch,
    message_id,
    transport,
):
    monkeypatch.setitem(
        config._data["notifications"],
        "dell_idrac",
        {
            "suppress_ipmi_session_audit_from": [
                "192.168.0.164",
                "192.168.0.251",
            ],
        },
    )
    value = payload("dell_storage.json")
    value["Events"][0].update({
        "MessageId": message_id,
        "Message": (
            "Successfully logged in using root, from 192.168.0.164 "
            f"and {transport}."
        ),
    })
    item = RedfishParser().parse(value, "dell")[0]

    assert DeliveryRouter().route(item) is True


@pytest.mark.parametrize(
    ("message_id", "source_ip", "message"),
    [
        ("USR0030", "192.168.0.99", "IPMI over LAN"),
        ("USR0031", "192.168.0.164", "IPMI over LAN login failed"),
    ],
)
def test_dell_suppression_preserves_untrusted_and_other_security_events(
    monkeypatch,
    message_id,
    source_ip,
    message,
):
    monkeypatch.setitem(
        config._data["notifications"],
        "dell_idrac",
        {"suppress_ipmi_session_audit_from": ["192.168.0.164"]},
    )
    item = Notification(
        source="dell_idrac",
        category="security",
        title=message,
        body=message,
        metadata={
            "message_id": message_id,
            "source_ip": source_ip,
        },
    )
    router = DeliveryRouter()
    router.outputs = {}

    assert router.route(item) is False


@pytest.mark.parametrize(
    ("fixture", "source", "system", "status"),
    (
        ("supermicro_alert.eml", "supermicro", "synthetic-smc-01", "warning"),
        ("hpe_alert.eml", "hpe_ilo", "synthetic-ilo-01", "warning"),
        ("dell_alert.eml", "dell_idrac", "synthetic-idrac-01", "failure"),
    ),
)
def test_vendor_email_candidates_are_dispatched(fixture, source, system, status):
    item = Dispatcher().parse(email(fixture))
    assert item.source == source
    assert item.metadata["system"] == system
    assert item.status == status
    assert item.start_time.startswith("2026-07-15T20:")


def test_redfish_endpoint_requires_token_and_suppresses_duplicates():
    value = payload("supermicro_thermal.json")
    with RunningServer() as running:
        port = running.server.server_port
        missing = post(port, "/redfish/supermicro", value)
        first = post(port, "/redfish/supermicro", value, "synthetic-redfish-secret")
        duplicate = post(port, "/redfish/supermicro", value, "synthetic-redfish-secret")

    assert (missing, first, duplicate) == (401, 204, 204)
    assert len(running.router.notifications) == 1




def test_disabled_redfish_input_is_acknowledged_without_delivery(monkeypatch):
    current = json.loads(json.dumps(config._data))
    current["redfish"] = {**(current.get("redfish") or {}), "enabled": False}
    monkeypatch.setattr(config, "_data", current)
    value = payload("supermicro_thermal.json")
    with RunningServer() as running:
        status = post(
            running.server.server_port,
            "/redfish/supermicro",
            value,
            "synthetic-redfish-secret",
        )
    assert status == 204
    assert running.router.notifications == []


def test_invalid_and_oversized_redfish_envelopes_are_rejected():
    assert RedfishParser.is_envelope({"Events": []}) is False
    assert RedfishParser.is_envelope({"Events": [{}]}) is False
    assert RedfishParser.is_envelope({"Events": [{"Message": "x"}] * 65}) is False


def test_hardware_formatters_are_registered_bounded_and_hide_fingerprint():
    item = RedfishParser().parse(payload("dell_storage.json"), "dell")[0]
    item.title = "T" * 800
    item.body = "B" * 8000
    discord = DellIDRACDiscordFormatter().format(item)
    teams = DellIDRACTeamsFormatter().format(item)
    rendered = json.dumps({"discord": discord, "teams": teams})

    assert isinstance(DiscordOutput().source_formatters["supermicro"], SupermicroDiscordFormatter)
    assert isinstance(DiscordOutput().source_formatters["hpe_ilo"], HPEILODiscordFormatter)
    assert isinstance(TeamsOutput().source_formatters["supermicro"], SupermicroTeamsFormatter)
    assert isinstance(TeamsOutput().source_formatters["hpe_ilo"], HPEILOTeamsFormatter)
    assert len(discord["embeds"][0]["title"]) <= 256
    assert len(teams["attachments"][0]["content"]["body"][0]["text"]) <= 512
    assert item.metadata["deduplication_key"] not in rendered
