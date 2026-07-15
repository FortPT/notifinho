"""Cross-source card presentation and outbound safety contract."""

from __future__ import annotations

import json

import pytest

import outputs.discord as discord_output_module
import outputs.teams as teams_output_module

from formatters.presentation import PresentationMixin
from models import Notification
from outputs.discord import DiscordOutput
from outputs.teams import TeamsOutput


def _notification(source: str) -> Notification:
    item = Notification(
        source=source,
        category="storage",
        status="warning",
        title="Synthetic presentation warning",
        body="Synthetic presentation event.",
        job_name="Synthetic XO backup",
        start_time="2026-07-15T01:15:00Z",
        end_time="2026-07-15T01:20:00Z",
        duration="5 min",
    )
    item.metadata = {
        "host": "synthetic-host",
        "hostname": "synthetic-host",
        "problem_name": "Synthetic Zabbix problem",
        "severity": "warning",
        "event_time": "2026-07-15T01:15:00Z",
        "nas_name": "synthetic-nas",
        "application": "Synthetic application",
        "event_type": "storage warning",
        "message": "Synthetic presentation event.",
        "alert_name": "Synthetic Grafana alert",
        "state": "warning",
        "alert_count": 1,
        "alerts": [
            {
                "event_type": "new",
                "message": "Synthetic TrueNAS alert.",
            }
        ],
        "controller": "synthetic-controller",
        "client_display_name": "synthetic-client",
        "wifi_name": "synthetic-wifi",
        "trigger_key": "motion",
        "trigger_device": "Synthetic camera",
        "system": "synthetic-drive",
        "backup_task": "Synthetic backup",
        "instance": "synthetic-portainer",
        "alert_source": "portainer",
        "node": "synthetic-pve",
        "storage": "synthetic-storage",
        "model": "SYNTHETIC-MODEL",
        "storage_pool": "Synthetic Pool",
    }
    return item


def _teams_content(payload: dict) -> dict:
    return payload["attachments"][0]["content"]


def _contains_image(value) -> bool:
    if isinstance(value, dict):
        return value.get("type") == "Image" or any(
            _contains_image(item) for item in value.values()
        )
    if isinstance(value, list):
        return any(_contains_image(item) for item in value)
    return False


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-07-15T01:15:00Z", "15 Jul 2026 • 01:15 UTC"),
        ("2026-07-15 16:39:00", "15 Jul 2026 • 16:39"),
        ("12th July 2026 06:00", "12 Jul 2026 • 06:00"),
    ],
)
def test_shared_datetime_contract(value, expected):
    assert PresentationMixin()._format_datetime(value) == expected


@pytest.mark.parametrize(
    "source",
    [
        "zabbix",
        "qnap",
        "grafana",
        "truenas",
        "unifi_network",
        "unifi_protect",
        "unifi_drive",
        "portainer",
        "proxmox",
        "synology",
        "redfish",
        "supermicro",
        "hpe_ilo",
        "dell_idrac",
        "home_assistant",
    ],
)
def test_every_dedicated_discord_card_has_a_product_thumbnail(source):
    formatter = DiscordOutput().source_formatters[source]
    embed = formatter.format(_notification(source))["embeds"][0]

    assert embed["thumbnail"]["url"].startswith("https://")
    assert embed["thumbnail"]["url"].endswith(".png")


@pytest.mark.parametrize(
    "source",
    [
        "zabbix",
        "qnap",
        "grafana",
        "truenas",
        "unifi_network",
        "unifi_protect",
        "unifi_drive",
        "portainer",
        "proxmox",
        "synology",
        "redfish",
        "supermicro",
        "hpe_ilo",
        "dell_idrac",
        "home_assistant",
    ],
)
def test_every_dedicated_teams_card_has_a_top_right_product_icon(source):
    formatter = TeamsOutput().source_formatters[source]
    card = _teams_content(formatter.format(_notification(source)))

    assert card["body"][0]["type"] == "ColumnSet"
    assert _contains_image(card["body"][0])


def test_xo_cards_keep_the_xen_orchestra_branding():
    item = _notification("xo")
    discord = DiscordOutput().default_formatter.format(item)["embeds"][0]
    teams = _teams_content(TeamsOutput().default_formatter.format(item))

    assert "xologoname.png" in discord["thumbnail"]["url"]
    assert _contains_image(teams["body"][0])


@pytest.mark.parametrize(
    ("output_class", "output_module"),
    [
        (DiscordOutput, discord_output_module),
        (TeamsOutput, teams_output_module),
    ],
)
def test_outputs_recursively_redact_credentials_before_delivery(
    monkeypatch,
    output_class,
    output_module,
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
        captured["payload"] = json
        return Response()

    item = _notification("portainer")
    item.body = (
        "token=super-secret password: hidden-value "
        "Authorization: Bearer private-bearer "
        "https://discord.com/api/webhooks/123/private-webhook"
    )

    monkeypatch.setattr(output_module, "config", Config())
    monkeypatch.setattr(output_module.requests, "post", fake_post)

    assert output_class().send(item, target="portainer")
    serialized = json.dumps(captured["payload"])

    assert "super-secret" not in serialized
    assert "hidden-value" not in serialized
    assert "private-bearer" not in serialized
    assert "private-webhook" not in serialized
    assert serialized.count("<redacted>") >= 4
