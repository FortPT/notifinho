"""Cross-source card presentation and outbound safety contract."""

from __future__ import annotations

import json
import struct

from pathlib import Path

import pytest

import outputs.discord as discord_output_module
import outputs.teams as teams_output_module

from formatters.presentation import PresentationMixin
from formatters.teams_common import TeamsCardFormatter
from models import Notification
from outputs.discord import DiscordOutput
from outputs.teams import TeamsOutput


ROOT = Path(__file__).resolve().parents[1]

TEAMS_PRODUCT_ASSETS = {
    "xo": "xen-orchestra.png",
    "grafana": "grafana.png",
    "portainer": "portainer.png",
    "proxmox": "proxmox.png",
    "qnap": "qnap.png",
    "synology": "synology.png",
    "truenas": "truenas.png",
    "unifi_network": "unifi-network.png",
    "unifi_protect": "unifi-protect.png",
    "unifi_drive": "unifi-drive.png",
    "zabbix": "zabbix.png",
    "redfish": "redfish.png",
    "supermicro": "supermicro.png",
    "hpe_ilo": "hpe-ilo.png",
    "dell_idrac": "dell-idrac.png",
    "home_assistant": "home-assistant.png",
    "generic": "notifinho.png",
}


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


def _image_urls(value) -> list[str]:
    if isinstance(value, dict):
        urls = [value["url"]] if value.get("type") == "Image" else []
        for item in value.values():
            urls.extend(_image_urls(item))
        return urls
    if isinstance(value, list):
        urls = []
        for item in value:
            urls.extend(_image_urls(item))
        return urls
    return []


def _header_image(header: dict) -> dict:
    return header["columns"][1]["items"][0]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-07-15T01:15:00Z", "15 Jul 2026 • 01:15"),
        ("2026-07-20T18:09:00+05:00", "20 Jul 2026 • 18:09"),
        ("2026-07-15 16:39:00", "15 Jul 2026 • 16:39"),
        ("12th July 2026 06:00", "12 Jul 2026 • 06:00"),
    ],
)
def test_shared_datetime_contract(value, expected):
    assert PresentationMixin()._format_datetime(value) == expected


def test_resolved_state_wins_over_previous_critical_severity():
    assert TeamsCardFormatter._teams_status("success", "disaster") == (
        "✅",
        "Good",
        "Resolved",
    )


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


@pytest.mark.parametrize(
    ("source", "filename"),
    TEAMS_PRODUCT_ASSETS.items(),
)
def test_every_teams_integration_uses_its_exact_product_asset(source, filename):
    item = _notification("home_lab" if source == "generic" else source)
    formatter = (
        TeamsOutput().default_formatter
        if source == "generic"
        else TeamsOutput().source_formatters[source]
    )
    header = _teams_content(formatter.format(item))["body"][0]

    assert _image_urls(header) == [
        f"{PresentationMixin.ICON_BASE_URL}/{filename}"
    ]


@pytest.mark.parametrize(
    ("source", "pixels"),
    [
        ("grafana", 48),
        ("proxmox", 64),
        ("qnap", 72),
        ("synology", 64),
        ("unifi_network", 80),
        ("unifi_protect", 80),
        ("unifi_drive", 64),
        ("redfish", 56),
        ("supermicro", 64),
        ("hpe_ilo", 64),
        ("dell_idrac", 80),
    ],
)
def test_teams_product_assets_use_legible_aspect_safe_sizes(source, pixels):
    header = _teams_content(
        TeamsOutput().source_formatters[source].format(_notification(source))
    )["body"][0]
    image = _header_image(header)

    assert image["width"] == f"{pixels}px"
    assert image["height"] == f"{pixels}px"


@pytest.mark.parametrize("filename", TEAMS_PRODUCT_ASSETS.values())
def test_every_teams_product_asset_is_256px_transparent_png(filename):
    data = (ROOT / "assets" / "icons" / filename).read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    width, height, _depth, color_type, _compression, _filter, _interlace = (
        struct.unpack(">IIBBBBB", data[16:29])
    )
    assert (width, height) == (256, 256)
    assert color_type in {4, 6}


def test_placeholder_unifi_badge_and_generated_sources_are_removed():
    assert not (ROOT / "assets" / "icons" / "unifi.png").exists()
    assert not (ROOT / "assets" / "icons" / "source").exists()


def test_xo_cards_keep_the_xen_orchestra_branding():
    item = _notification("xo")
    discord = DiscordOutput().source_formatters["xo"].format(item)["embeds"][0]
    teams = _teams_content(TeamsOutput().source_formatters["xo"].format(item))

    assert discord["thumbnail"]["url"].endswith("/xen-orchestra.png")
    assert _contains_image(teams["body"][0])


def test_xo_card_uses_backup_name_and_omits_missing_duration_and_result():
    item = _notification("xo")
    item.job_name = "Nightly Production Backup"
    item.duration = ""
    item.vm_success = 0
    item.vm_failed = 0
    item.vm_skipped = 0
    card = _teams_content(TeamsOutput().source_formatters["xo"].format(item))
    rendered = json.dumps(card, ensure_ascii=False)

    assert "Nightly Production Backup" in card["body"][0]["text"]
    assert "Duration" not in rendered
    assert "Result" not in rendered


def test_xo_card_retains_real_duration_and_result_values():
    item = _notification("xo")
    item.duration = "5 min"
    item.vm_success = 3
    card = _teams_content(TeamsOutput().source_formatters["xo"].format(item))
    rendered = json.dumps(card, ensure_ascii=False)

    assert '"value": "5 min"' in rendered
    assert '"value": "✅ 3 of 3 VMs successful"' in rendered


def test_xo_result_explains_failed_and_skipped_counts():
    item = _notification("xo")
    item.vm_total = 4
    item.vm_success = 2
    item.vm_failed = 1
    item.vm_skipped = 1
    card = _teams_content(TeamsOutput().source_formatters["xo"].format(item))
    rendered = json.dumps(card, ensure_ascii=False)

    assert (
        '"value": "✅ 2 of 4 VMs successful • '
        '❌ 1 failed • ⚠️ 1 skipped"'
    ) in rendered


def test_identifier_labels_preserve_source_acronyms_and_hyphens():
    assert TeamsCardFormatter._label("PVE-01") == "PVE-01"
    assert TeamsCardFormatter._label("CPU usage") == "CPU Usage"
    assert TeamsCardFormatter._label("VMID") == "VMID"


def test_generic_events_do_not_fall_back_to_xen_orchestra_cards():
    item = _notification("home_lab")
    item.job_name = ""
    item.metadata.update({
        "provider": "home_lab",
        "environment": "synthetic",
        "action_link": "https://example.invalid/events/validation",
    })

    discord = DiscordOutput().default_formatter.format(item)["embeds"][0]
    teams = _teams_content(TeamsOutput().default_formatter.format(item))
    rendered = json.dumps(
        {"discord": discord, "teams": teams},
        ensure_ascii=False,
    )

    assert "Synthetic presentation warning" in rendered
    assert "Synthetic presentation event." in rendered
    assert "home_lab" in rendered
    assert "15 Jul 2026 • 01:15" in rendered
    assert "UTC" not in rendered
    assert "Xen Orchestra" not in rendered
    assert "Backup Successful" not in rendered
    assert "xologoname.png" not in rendered
    assert "notifinho.png" in rendered


@pytest.mark.parametrize(
    "source",
    [
        "xo",
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
def test_every_teams_card_uses_the_shared_information_hierarchy(source):
    card = _teams_content(
        TeamsOutput().source_formatters[source].format(_notification(source))
    )

    assert card["body"][0]["type"] == "ColumnSet"
    assert " • " in card["body"][0]["text"]
    assert card["body"][1]["type"] == "TextBlock"
    assert card["body"][2]["type"] == "Container"
    assert card["body"][2]["style"] == "emphasis"
    metrics = card["body"][3]
    assert metrics["type"] == "ColumnSet"
    assert [
        column["items"][0]["text"].split(" ", 1)[1]
        for column in metrics["columns"]
    ] == ["Severity", "Category", "Event time"]
    assert metrics["columns"][2]["items"][1]["text"] == (
        "15 Jul 2026 • 01:15"
        if source != "xo"
        else "15 Jul 2026 • 01:20"
    )


def test_xo_and_generic_formatters_are_selected_explicitly():
    discord = DiscordOutput()
    teams = TeamsOutput()

    assert discord.source_formatters["xo"].__class__.__name__ == "DiscordFormatter"
    assert teams.source_formatters["xo"].__class__.__name__ == "TeamsFormatter"
    assert discord.default_formatter.__class__.__name__ == "GenericDiscordFormatter"
    assert teams.default_formatter.__class__.__name__ == "GenericTeamsFormatter"


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


@pytest.mark.parametrize(
    "webhook",
    ["PASTE_HERE", "http://example.invalid/hook", "not-a-url", ""],
)
def test_teams_rejects_placeholder_or_insecure_webhooks_before_delivery(
    monkeypatch,
    webhook,
):
    calls = []

    class Config:
        def get(self, *keys, default=None):
            return webhook if keys[-1:] == ("webhook",) else default

    monkeypatch.setattr(teams_output_module, "config", Config())
    monkeypatch.setattr(
        teams_output_module.requests,
        "post",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    assert not TeamsOutput().send(_notification("truenas"), target="truenas")
    assert calls == []
