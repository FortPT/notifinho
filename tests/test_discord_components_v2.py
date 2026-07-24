"""Focused Discord Components V2 prototype coverage."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from formatters.discord_hardware import DellIDRACDiscordFormatter
from models import Notification
from outputs.discord import DiscordOutput
import outputs.discord as discord_output_module


ALL_DISCORD_SOURCES = (
    "xo",
    "grafana",
    "portainer",
    "proxmox",
    "qnap",
    "synology",
    "truenas",
    "unifi_network",
    "unifi_protect",
    "unifi_drive",
    "zabbix",
    "redfish",
    "supermicro",
    "hpe_ilo",
    "dell_idrac",
    "home_assistant",
    "generic",
)


def integration_notification(source: str) -> Notification:
    item = Notification(
        source="home_lab" if source == "generic" else source,
        title="Synthetic responsive event",
        body="Synthetic responsive operational detail.",
        category="storage",
        status="warning",
        job_name="Synthetic XO backup",
        start_time="2026-07-20T23:31:00+00:00",
        end_time="2026-07-20T23:36:00+00:00",
        duration="5 min",
    )
    item.metadata = {
        "provider": "Generic Webhook",
        "host": "SYNTHETIC-HOST",
        "hostname": "SYNTHETIC-HOST",
        "system": "SYNTHETIC-SYSTEM",
        "nas_name": "SYNTHETIC-NAS",
        "instance": "SYNTHETIC-INSTANCE",
        "device": "SYNTHETIC-DEVICE",
        "area": "Synthetic area",
        "service": "synthetic.service",
        "entity_id": "sensor.synthetic",
        "node": "SYNTHETIC-PVE",
        "controller": "SYNTHETIC-UDM",
        "client_display_name": "SYNTHETIC-CLIENT",
        "wifi_name": "SYNTHETIC-WIFI",
        "trigger_key": "motion",
        "trigger_device": "CAM-SYNTHETIC-01",
        "alarm_name": "Synthetic Protect alarm",
        "backup_task": "Synthetic backup",
        "problem_name": "Synthetic Zabbix problem",
        "alert_name": "Synthetic Grafana alert",
        "alert_count": 1,
        "folder": "Synthetic folder",
        "dashboard": "Synthetic dashboard",
        "panel": "Synthetic panel",
        "operational_data": "Synthetic operational state",
        "event_type": "storage warning",
        "severity": "warning",
        "event_time": "2026-07-20T23:31:00+00:00",
        "state": "warning",
        "message": "Synthetic responsive operational detail.",
        "model": "SYNTHETIC-MODEL",
        "storage_pool": "Synthetic Pool",
        "sensor": "Synthetic sensor",
        "registry": "Synthetic registry",
        "message_id": "Synthetic.Message",
        "origin": "/synthetic/origin",
    }
    return item


def dell_notification() -> Notification:
    return Notification(
        source="dell_idrac",
        title="Power Supply Recovered",
        body="The power supply returned to a healthy state.",
        category="power",
        status="resolved",
        start_time="2026-07-20T23:31:00+00:00",
        metadata={
            "provider": "Dell iDRAC",
            "system": "DELL-SRV-01",
            "severity": "Ok",
            "sensor": "PSU 1",
            "registry": "iDRAC",
            "message_id": "iDRAC.Audit.Power",
            "origin": "/redfish/v1/Chassis/1/Power",
        },
    )


def child_components(payload: dict) -> list[dict]:
    return payload["components"][0]["components"]


def text_content(payload: dict) -> str:
    values = []

    def visit(component):
        if isinstance(component, dict):
            if component.get("type") == 10:
                values.append(component["content"])
            for value in component.values():
                visit(value)
        elif isinstance(component, list):
            for value in component:
                visit(value)

    visit(payload["components"])
    return "\n".join(values)


def flattened_components(payload: dict) -> list[dict]:
    values = []

    def visit(component):
        if isinstance(component, dict):
            if "type" in component:
                values.append(component)
            for value in component.values():
                visit(value)
        elif isinstance(component, list):
            for value in component:
                visit(value)

    visit(payload["components"])
    return values


def test_dell_components_v2_uses_native_responsive_separators():
    formatter = DellIDRACDiscordFormatter()
    payload = formatter.format_components_v2(dell_notification())

    assert set(payload) == {"flags", "components"}
    assert payload["flags"] == 32768
    assert len(payload["components"]) == 1

    container = payload["components"][0]
    assert container["type"] == 17
    assert container["accent_color"] == 0x2ECC71

    children = child_components(payload)
    assert children[0]["type"] == 9
    assert children[0]["accessory"]["type"] == 11
    assert children[0]["accessory"]["media"]["url"].endswith(
        "/dell-idrac.png"
    )

    separators = [child for child in children if child["type"] == 14]
    assert [separator["divider"] for separator in separators] == [
        True,
        False,
        True,
        True,
    ]
    assert all(separator["spacing"] == 1 for separator in separators)

    header_text = children[0]["components"][0]["content"]
    context_text = children[0]["components"][1]["content"]
    assert "DELL-SRV-01 • Power Supply Recovered" in header_text
    assert "Dell iDRAC • ✅ **Resolved** • 🔌 Power" in context_text
    assert "Dell iDRAC" not in header_text
    assert children[1]["type"] == 14
    assert children[1]["divider"] is True
    assert children[2]["content"].startswith("```\n")

    rendered = text_content(payload)
    assert "DELL-SRV-01 • Power Supply Recovered" in rendered
    assert "Dell iDRAC • ✅ **Resolved** • 🔌 Power" in rendered
    assert "The power supply returned to a healthy state." in rendered
    assert "✅ **Severity:** Ok" in rendered
    assert "🔌 **Category:** Power" in rendered
    assert "🕒 **Event time:**" in rendered
    assert "🌡️ **Sensor:** PSU 1" in rendered
    assert "📍 **Origin:** /redfish/v1/Chassis/1/Power" in rendered
    assert "FortPT Labs • Notifinho v2.4.0" in rendered
    assert "─" not in rendered
    assert "embeds" not in payload
    assert "attachments" not in payload
    assert len(flattened_components(payload)) <= 40
    assert len(rendered) <= 4000


def test_every_discord_integration_uses_approved_components_v2_contract():
    output = DiscordOutput()

    for source in ALL_DISCORD_SOURCES:
        formatter = (
            output.default_formatter
            if source == "generic"
            else output.source_formatters[source]
        )
        payload = formatter.format_components_v2(
            integration_notification(source)
        )

        assert payload["flags"] == 32768, source
        assert "embeds" not in payload, source
        assert "attachments" not in payload, source
        container = payload["components"][0]
        assert container["type"] == 17, source
        children = container["components"]
        header = children[0]
        assert header["type"] == 9, source
        assert len(header["components"]) == 2, source
        assert header["accessory"]["type"] == 11, source
        assert header["accessory"]["media"]["url"].endswith(".png"), source
        assert children[1] == {
            "type": 14,
            "divider": True,
            "spacing": 1,
        }, source
        assert children[2]["type"] == 10, source
        assert children[2]["content"].startswith("```\n"), source
        separators = [
            component
            for component in children
            if component.get("type") == 14
        ]
        assert [item["divider"] for item in separators] == [
            True,
            False,
            True,
            True,
        ], source
        assert all(item["spacing"] == 1 for item in separators), source
        rendered = text_content(payload)
        assert "**Severity:**" in rendered, source
        assert "**Category:**" in rendered, source
        assert "**Event time:**" in rendered, source
        assert "📋 Event details" in rendered, source
        assert "FortPT Labs • Notifinho v2.4.0" in rendered, source
        assert len(flattened_components(payload)) <= 40, source
        assert len(rendered) <= 4000, source


def test_dell_components_v2_delivery_enables_webhook_components(monkeypatch):
    captured = {}

    class Config:
        def get(self, *keys, default=None):
            if keys[-1:] == ("webhook",):
                return (
                    "https://discord.com/api/webhooks/123/token"
                    "?wait=true"
                )
            return default

    class Response:
        status_code = 204
        text = ""

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["payload"] = json
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(discord_output_module, "config", Config())
    monkeypatch.setattr(discord_output_module.requests, "post", fake_post)

    assert DiscordOutput().send(dell_notification(), target="alfa")

    query = parse_qs(urlsplit(captured["url"]).query)
    assert query == {"wait": ["true"], "with_components": ["true"]}
    assert captured["payload"]["flags"] == 32768
    assert "components" in captured["payload"]
    assert "embeds" not in captured["payload"]
    assert "attachments" not in captured["payload"]
    assert captured["timeout"] == 15


def test_inherited_components_v2_contract_is_used_for_delivery(monkeypatch):
    captured = {}

    class Config:
        def get(self, *keys, default=None):
            if keys[-1:] == ("webhook",):
                return "https://discord.com/api/webhooks/123/token"
            return default

    class Response:
        status_code = 204
        text = ""

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["payload"] = json
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(discord_output_module, "config", Config())
    monkeypatch.setattr(discord_output_module.requests, "post", fake_post)

    item = integration_notification("qnap")
    assert DiscordOutput().send(item, target="qnap")

    query = parse_qs(urlsplit(captured["url"]).query)
    assert query == {"with_components": ["true"]}
    assert captured["payload"]["flags"] == 32768
    assert "components" in captured["payload"]
    assert "embeds" not in captured["payload"]
    assert "attachments" not in captured["payload"]
    assert captured["timeout"] == 15


def test_components_v2_context_does_not_change_direct_legacy_formatting():
    formatter = DiscordOutput().source_formatters["qnap"]
    item = integration_notification("qnap")

    responsive = formatter.format_components_v2(item)
    legacy = formatter.format(item)

    assert responsive["flags"] == 32768
    assert "components" in responsive
    assert set(legacy) == {"embeds"}


def test_legacy_discord_payload_does_not_change_webhook_url():
    webhook = "https://discord.com/api/webhooks/123/token?wait=true"

    assert DiscordOutput._delivery_webhook(
        webhook,
        {"embeds": [{"title": "Legacy"}]},
    ) == webhook
