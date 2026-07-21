"""Focused Discord Components V2 prototype coverage."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from formatters.discord_hardware import DellIDRACDiscordFormatter
from models import Notification
from outputs.discord import DiscordOutput
import outputs.discord as discord_output_module


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
        False,
        True,
        True,
    ]
    assert all(separator["spacing"] == 1 for separator in separators)

    header_text = children[0]["components"][0]["content"]
    context_text = children[1]["content"]
    assert "DELL-SRV-01 • Power Supply Recovered" in header_text
    assert "Dell iDRAC • ✅ **Resolved** • 🔌 Power" in context_text
    assert "Dell iDRAC" not in header_text
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
    assert "FortPT Labs • Notifinho v1.9.5" in rendered
    assert "─" not in rendered
    assert "embeds" not in payload
    assert "attachments" not in payload
    assert len(flattened_components(payload)) <= 40
    assert len(rendered) <= 4000


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


def test_legacy_discord_payload_does_not_change_webhook_url():
    webhook = "https://discord.com/api/webhooks/123/token?wait=true"

    assert DiscordOutput._delivery_webhook(
        webhook,
        {"embeds": [{"title": "Legacy"}]},
    ) == webhook
