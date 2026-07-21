"""Cross-source card presentation and outbound safety contract."""

from __future__ import annotations

import json
import struct

from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import outputs.discord as discord_output_module
import outputs.teams as teams_output_module

from config import config
from formatters.discord_common import DiscordCardFormatter
from formatters.presentation import PresentationMixin
from formatters.teams_common import TeamsCardFormatter
from models import Notification
from outputs.discord import DiscordOutput
from outputs.teams import TeamsOutput
from version import VERSION


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
        ("2026-07-20T18:09:00+05:00", "20 Jul 2026 • 13:09"),
        ("2026-07-15 16:39:00", "15 Jul 2026 • 16:39"),
        ("12th July 2026 06:00", "12 Jul 2026 • 06:00"),
    ],
)
def test_shared_datetime_contract(value, expected):
    assert PresentationMixin()._format_datetime(value) == expected


@pytest.mark.parametrize("value", [1784583600, "1784583600000"])
def test_epoch_uses_configured_iana_timezone(monkeypatch, value):
    monkeypatch.setitem(
        config._data,
        "presentation",
        {"timezone": "Europe/Lisbon"},
    )

    assert PresentationMixin()._format_datetime(value) == (
        "20 Jul 2026 • 22:40"
    )


def test_explicit_offset_converts_to_local_presentation_time(monkeypatch):
    monkeypatch.setitem(
        config._data,
        "presentation",
        {"timezone": "Europe/Lisbon"},
    )

    assert PresentationMixin()._format_datetime(
        "2026-07-20T18:09:00+05:00"
    ) == "20 Jul 2026 • 14:09"


def test_machine_local_timezone_is_the_default(monkeypatch):
    monkeypatch.setitem(config._data, "presentation", {})
    monkeypatch.delenv("TZ", raising=False)
    monkeypatch.setattr(
        "formatters.presentation.get_localzone",
        lambda: ZoneInfo("Europe/Lisbon"),
    )

    assert PresentationMixin()._format_datetime(
        "2026-07-20T22:47:00Z"
    ) == "20 Jul 2026 • 23:47"


def test_resolved_state_wins_over_previous_critical_severity():
    assert TeamsCardFormatter._teams_status("success", "disaster") == (
        "✅",
        "Good",
        "Resolved",
    )

    assert DiscordCardFormatter._discord_status("success", "disaster") == (
        "✅",
        0x2ECC71,
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
    ("source", "filename"),
    TEAMS_PRODUCT_ASSETS.items(),
)
def test_every_discord_integration_uses_its_exact_official_product_asset(
    source,
    filename,
):
    item = _notification("home_lab" if source == "generic" else source)
    formatter = (
        DiscordOutput().default_formatter
        if source == "generic"
        else DiscordOutput().source_formatters[source]
    )
    embed = formatter.format(item)["embeds"][0]

    assert embed["thumbnail"]["url"] == (
        f"{PresentationMixin.ICON_BASE_URL}/{filename}"
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

    discord = DiscordOutput().source_formatters["xo"].format(item)["embeds"][0]
    discord_rendered = json.dumps(discord, ensure_ascii=False)
    assert "⏱️ **Duration:** 5 min" in discord_rendered
    assert "📊 **Result:** ✅ 3 of 3 VMs successful" in discord_rendered


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
        "generic",
    ],
)
def test_every_discord_card_uses_the_shared_information_hierarchy(source):
    output = DiscordOutput()
    formatter = (
        output.default_formatter
        if source == "generic"
        else output.source_formatters[source]
    )
    embed = formatter.format(_notification(source))["embeds"][0]

    assert " • " in embed["title"]
    assert not embed["description"].startswith("\u200b\n")
    assert not embed["description"].startswith("\n")
    assert "\n\n" not in embed["description"]
    assert embed["description"].count(" • ") == 2
    assert [field["name"].split(" ", 1)[-1] for field in embed["fields"][:3]] == [
        "Severity",
        "Category",
        "Event time",
    ]
    assert embed["description"].endswith("\n```")
    assert (
        f"\n{formatter.SEPARATOR}\n```\n"
        in embed["description"]
    )
    assert len(formatter.SEPARATOR) == 47
    assert embed["description"].count(formatter.SEPARATOR) == 1
    assert all(field["inline"] is True for field in embed["fields"][:3])
    assert embed["fields"][2]["value"] == (
        "15 Jul 2026 • 01:20"
        if source == "xo"
        else "15 Jul 2026 • 01:15"
    )
    assert len(embed["fields"]) <= 25
    assert formatter._embed_text_size(embed) <= formatter.EMBED_TEXT_BUDGET
    assert embed["fields"][-1]["value"].endswith(formatter.SEPARATOR)
    assert all(
        "Event" != field["name"].split(" ", 1)[-1]
        for field in embed["fields"]
    )
    field_separator_count = sum(
        str(field["value"]).count(formatter.SEPARATOR)
        for field in embed["fields"]
    )
    has_details = any(
        "📋 **Event details**" in str(field["value"])
        for field in embed["fields"]
    )
    assert field_separator_count == (2 if has_details else 1)
    assert embed["footer"]["text"] == f"FortPT Labs • Notifinho v{VERSION}"


def test_discord_details_follow_metrics_and_end_at_the_footer_rule():
    item = _notification("proxmox")
    item.metadata.update({
        "vmid": 101,
        "guest": "APP-01",
        "job_id": "vzdump-nightly",
        "storage": "backup-nfs",
    })
    embed = DiscordOutput().source_formatters["proxmox"].format(item)["embeds"][0]

    details_index = next(
        index
        for index, field in enumerate(embed["fields"])
        if "📋 **Event details**" in field["value"]
    )
    details = embed["fields"][details_index]

    assert embed["fields"][details_index - 1]["name"].endswith("Event time")
    assert details["name"] == "\u200b"
    assert details["inline"] is False
    assert details["value"].startswith(
        f"{DiscordCardFormatter.SEPARATOR}\n📋 **Event details**\n"
    )
    assert "🆔 **VMID:** 101" in details["value"]
    assert "💻 **Guest:** APP-01" in details["value"]
    assert details["value"].endswith(DiscordCardFormatter.SEPARATOR)
    assert not details["value"].endswith(
        f"\n\n{DiscordCardFormatter.SEPARATOR}"
    )


def test_discord_converts_source_time_and_never_invents_receipt_time():
    item = _notification("generic")
    item.start_time = ""
    item.metadata["event_time"] = "2026-07-20T18:09:00+05:00"
    embed = DiscordOutput().default_formatter.format(item)["embeds"][0]

    assert embed["fields"][2]["value"] == "20 Jul 2026 • 13:09"
    assert "UTC" not in json.dumps(embed)

    item.metadata["event_time"] = ""
    missing = DiscordOutput().default_formatter.format(item)["embeds"][0]
    assert all(
        field["name"].split(" ", 1)[-1] != "Event time"
        for field in missing["fields"]
    )


def test_discord_rich_details_survive_the_shared_renderer():
    item = _notification("proxmox")
    item.metadata.update({
        "vmid": 101,
        "guest": "APP-01",
        "job_id": "vzdump-nightly",
        "storage": "backup-nfs",
    })
    item.duration = "4 min 31 sec"
    rendered = json.dumps(
        DiscordOutput().source_formatters["proxmox"].format(item),
        ensure_ascii=False,
    )

    for value in ("VMID", "101", "APP-01", "vzdump-nightly", "backup-nfs", "4 min 31 sec"):
        assert value in rendered


def test_xo_and_generic_formatters_are_selected_explicitly():
    discord = DiscordOutput()
    teams = TeamsOutput()

    assert discord.source_formatters["xo"].__class__.__name__ == "DiscordFormatter"
    assert teams.source_formatters["xo"].__class__.__name__ == "TeamsFormatter"
    assert discord.default_formatter.__class__.__name__ == "GenericDiscordFormatter"
    assert teams.default_formatter.__class__.__name__ == "GenericTeamsFormatter"


def test_discord_uploads_packaged_thumbnail_as_webhook_attachment(
    monkeypatch,
    tmp_path,
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

    icon = tmp_path / "redfish.png"
    icon.write_bytes(b"\x89PNG\r\n\x1a\nsynthetic")

    def fake_post(url, data, files, timeout):
        captured["url"] = url
        captured["payload"] = json.loads(data["payload_json"])
        captured["filename"] = files["files[0]"][0]
        captured["content"] = files["files[0]"][1].read()
        captured["mime"] = files["files[0]"][2]
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(discord_output_module, "config", Config())
    monkeypatch.setattr(discord_output_module.requests, "post", fake_post)
    monkeypatch.setattr(DiscordOutput, "ICON_DIR", tmp_path)

    assert DiscordOutput().send(_notification("redfish"), target="default")

    payload = captured["payload"]
    assert payload["embeds"][0]["thumbnail"]["url"] == (
        "attachment://redfish.png"
    )
    assert payload["attachments"] == [
        {"id": 0, "filename": "redfish.png"}
    ]
    assert captured["filename"] == "redfish.png"
    assert captured["content"].startswith(b"\x89PNG")
    assert captured["mime"] == "image/png"
    assert captured["timeout"] == 15


@pytest.mark.parametrize(
    ("source", "filename"),
    TEAMS_PRODUCT_ASSETS.items(),
)
def test_every_discord_product_thumbnail_resolves_to_a_packaged_asset(
    source,
    filename,
):
    item = _notification("home_lab" if source == "generic" else source)
    output = DiscordOutput()
    formatter = (
        output.default_formatter
        if source == "generic"
        else output.source_formatters[source]
    )
    payload = formatter.format(item)
    output.ICON_DIR = ROOT / "assets" / "icons"

    resolved = output._local_icon(payload, formatter)

    assert resolved == (filename, output.ICON_DIR / filename)


def test_container_image_packages_the_discord_icon_directory():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "COPY assets /notifinho/assets" in dockerfile


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
