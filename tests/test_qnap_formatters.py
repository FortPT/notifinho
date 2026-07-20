"""QNAP Discord and Microsoft Teams payload tests."""

from __future__ import annotations

import json

from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path

import pytest

import outputs.discord as discord_output_module
import outputs.teams as teams_output_module

from formatters.discord_qnap import QNAPDiscordFormatter
from formatters.teams_qnap import QNAPTeamsFormatter
from models import Notification
from outputs.discord import DiscordOutput
from outputs.teams import TeamsOutput
from parsers.qnap import Parser as QNAPParser
from version import VERSION


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "qnap"
    / "storage_warning.eml"
)


def storage_notification():

    with FIXTURE.open("rb") as fixture:

        message = BytesParser(
            policy=policy.default,
        ).parse(fixture)

    return QNAPParser().parse(
        message,
    )


def test_discord_payload_generation():

    payload = QNAPDiscordFormatter().format(
        storage_notification(),
    )

    assert list(payload) == ["embeds"]
    assert len(payload["embeds"]) == 1

    embed = payload["embeds"][0]

    assert "SYNTHETIC-QNAP-HERO" in embed["title"]
    assert "QNAP" in embed["description"]
    assert "Warning" in embed["description"]
    assert embed["color"] == 0xF39C12
    assert embed["footer"]["text"].endswith(
        f"Notifinho v{VERSION}"
    )
    assert embed["fields"]
    assert all(
        field["name"] and field["value"]
        for field in embed["fields"]
    )

    serialized = json.dumps(
        payload,
        ensure_ascii=False,
    )

    assert "Storage Pool 1 entered" in serialized
    assert "Storage Pool" in serialized
    assert "RAID Group" in serialized
    assert "Storage & Snapshots" in serialized
    assert "12 Jul 2026 • 08:30" in serialized

    assert not any(
        "2026/07/12 08" in field["name"]
        for field in embed["fields"]
    )
    assert not any(
        field["value"] == "30:00"
        for field in embed["fields"]
    )


def test_teams_payload_generation():

    payload = QNAPTeamsFormatter().format(
        storage_notification(),
    )

    assert payload["type"] == "message"
    assert len(payload["attachments"]) == 1

    attachment = payload["attachments"][0]

    assert attachment["contentType"] == (
        "application/vnd.microsoft.card.adaptive"
    )

    card = attachment["content"]

    assert card["type"] == "AdaptiveCard"
    assert card["version"] == "1.4"
    assert card["msteams"]["width"] == "Full"

    serialized = json.dumps(
        payload,
    )

    assert "SYNTHETIC-QNAP-HERO" in serialized
    assert "Storage Pool 1 entered" in serialized
    assert "Storage Pool" in serialized
    assert "RAID Group" in serialized
    assert "Storage & Snapshots" in serialized
    assert "Warning" in serialized
    assert f"Notifinho v{VERSION}" in serialized

    for item in _walk(card):

        if item.get("type") == "TextBlock":

            assert str(
                item.get(
                    "text",
                    "",
                )
            ).strip()

        if item.get("type") == "FactSet":

            assert all(
                fact.get("title") and fact.get("value")
                for fact in item.get("facts", [])
            )


def test_outputs_register_qnap_formatters_without_sending_webhooks():

    discord = DiscordOutput()
    teams = TeamsOutput()

    assert isinstance(
        discord.source_formatters["qnap"],
        QNAPDiscordFormatter,
    )

    assert isinstance(
        teams.source_formatters["qnap"],
        QNAPTeamsFormatter,
    )

    assert "zabbix" in discord.source_formatters
    assert "zabbix" in teams.source_formatters


def test_alert_severity_is_consistently_warning_colored():

    message = EmailMessage()
    message["From"] = "QNAP Notification Center <alerts@qnap.invalid>"
    message["Subject"] = "[QNAP] Synthetic alert"
    message.set_content(
        "NAS Name: SYNTHETIC-QNAP-LAB\n"
        "Severity: Alert\n"
        "Category: Security\n"
        "Message: Synthetic security alert",
    )

    notification = QNAPParser().parse(
        message,
    )

    discord = QNAPDiscordFormatter().format(
        notification,
    )["embeds"][0]

    teams = QNAPTeamsFormatter().format(
        notification,
    )

    assert notification.status == "warning"
    assert discord["color"] == 0xF39C12
    assert "Warning" in discord["description"]
    assert '"color": "Warning"' in json.dumps(
        teams,
    )


@pytest.mark.parametrize(
    (
        "status",
        "severity",
        "discord_color",
        "teams_color",
        "status_text",
    ),
    [
        (
            "success",
            "Normal",
            0x2ECC71,
            "Good",
            "Success",
        ),
        (
            "information",
            "Information",
            0x3498DB,
            "Accent",
            "Information",
        ),
        (
            "warning",
            "Warning",
            0xF39C12,
            "Warning",
            "Warning",
        ),
        (
            "warning",
            "Alert",
            0xF39C12,
            "Warning",
            "Warning",
        ),
        (
            "failure",
            "Critical",
            0xE74C3C,
            "Attention",
            "Failure",
        ),
        (
            "success",
            "Resolved",
            0x2ECC71,
            "Good",
            "Success",
        ),
    ],
)
def test_status_colors_are_aligned_across_outputs(
    status: str,
    severity: str,
    discord_color: int,
    teams_color: str,
    status_text: str,
):

    notification = Notification(
        source="qnap",
        category="system",
        status=status,
        metadata={
            "nas_name": "SYNTHETIC-QNAP-LAB",
            "category": "system",
            "severity": severity,
            "message": "Synthetic status event",
        },
    )

    discord = QNAPDiscordFormatter().format(
        notification,
    )["embeds"][0]

    teams_card = QNAPTeamsFormatter().format(
        notification,
    )["attachments"][0]["content"]

    assert discord["color"] == discord_color
    assert status_text in discord["description"]
    assert teams_card["body"][0]["color"] == teams_color
    assert status_text in teams_card["body"][1]["text"]


@pytest.mark.parametrize(
    (
        "fixture_name",
        "expected_details",
    ),
    [
        (
            "storage_warning.eml",
            (
                "Storage Pool",
                "RAID Group",
            ),
        ),
        (
            "hbs_backup_failure.eml",
            (
                "Job Name",
                "Destination",
            ),
        ),
        (
            "failed_login.eml",
            (
                "Account",
                "Connection Type",
            ),
        ),
        (
            "ups_power_event.eml",
            (
                "UPS Status",
                "Power Event",
            ),
        ),
        (
            "update_notice.eml",
            (
                "Current Version",
                "Available Version",
            ),
        ),
    ],
)
def test_event_specific_details_reach_both_payloads(
    fixture_name: str,
    expected_details: tuple[str, ...],
):

    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "qnap"
        / fixture_name
    )

    with fixture_path.open("rb") as fixture:

        message = BytesParser(
            policy=policy.default,
        ).parse(fixture)

    notification = QNAPParser().parse(
        message,
    )

    discord = json.dumps(
        QNAPDiscordFormatter().format(
            notification,
        )
    )

    teams = json.dumps(
        QNAPTeamsFormatter().format(
            notification,
        )
    )

    for expected in expected_details:

        assert expected in discord
        assert expected in teams


def test_missing_and_malformed_metadata_omits_empty_optional_values():

    notification = Notification(
        source="qnap",
        status="information",
        metadata={
            "application": "",
            "event_time": None,
            "message": "",
            "nas_name": None,
            "severity": "",
            "source_fields": "malformed",
        },
    )

    discord = QNAPDiscordFormatter().format(
        notification,
    )["embeds"][0]

    teams = QNAPTeamsFormatter().format(
        notification,
    )["attachments"][0]["content"]

    assert all(
        field["name"] and field["value"]
        for field in discord["fields"]
    )

    discord_text = json.dumps(
        discord,
    )

    teams_text = json.dumps(
        teams,
    )

    assert "Application" not in discord_text
    assert "Event time" not in discord_text
    assert "Application" not in teams_text
    assert "Event time" in teams_text
    assert "\\u2014" in teams_text


def test_discord_oversized_unknown_metadata_stays_inside_embed_budget():

    unknown_fields = {
        f"Synthetic Unknown Field {index}": "x" * 2000
        for index in range(40)
    }

    notification = Notification(
        source="qnap",
        category="storage",
        status="failure",
        metadata={
            "nas_name": "SYNTHETIC-QNAP-LAB",
            "application": "Storage & Snapshots",
            "category": "storage",
            "event_time": "2026-07-12 12:00:00",
            "event_type": "Storage Failure",
            "message": "Essential synthetic event message " + "m" * 1800,
            "severity": "Critical",
            "source_fields": unknown_fields,
        },
    )

    formatter = QNAPDiscordFormatter()
    embed = formatter.format(
        notification,
    )["embeds"][0]

    assert formatter._embed_text_size(embed) <= 5900
    assert formatter._embed_text_size(embed) <= 6000
    assert len(embed["title"]) <= 256
    assert len(embed["description"]) <= 4096
    assert len(embed["fields"]) <= 25
    assert all(
        len(field["name"]) <= 256
        and len(field["value"]) <= 1024
        for field in embed["fields"]
    )

    serialized = json.dumps(
        embed,
    )

    assert "Essential synthetic event message" in serialized
    assert "Critical" in serialized
    assert "Storage & Snapshots" in serialized
    assert any(
        field["value"].endswith("…")
        for field in embed["fields"]
    )


@pytest.mark.parametrize(
    (
        "output_class",
        "output_module",
        "payload_marker",
    ),
    [
        (
            DiscordOutput,
            discord_output_module,
            "embeds",
        ),
        (
            TeamsOutput,
            teams_output_module,
            "attachments",
        ),
    ],
)
def test_actual_output_send_selects_qnap_formatter_without_network(
    monkeypatch,
    output_class,
    output_module,
    payload_marker: str,
):

    captured = {}

    class Config:

        def get(
            self,
            *keys,
            default=None,
        ):

            if keys[-1:] == ("webhook",):

                return "https://example.invalid/webhook/synthetic/id"

            return default

    class Response:

        status_code = 204
        text = ""

    def fake_post(
        url,
        json,
        timeout,
    ):

        captured["url"] = url
        captured["payload"] = json
        captured["timeout"] = timeout

        return Response()

    monkeypatch.setattr(
        output_module,
        "config",
        Config(),
    )

    monkeypatch.setattr(
        output_module.requests,
        "post",
        fake_post,
    )

    assert output_class().send(
        storage_notification(),
    )

    assert payload_marker in captured["payload"]
    assert "SYNTHETIC-QNAP-HERO" in json.dumps(
        captured["payload"],
    )
    assert captured["url"].startswith(
        "https://example.invalid/"
    )
    assert captured["timeout"] == 15


def _walk(value):

    if isinstance(value, dict):

        yield value

        for nested in value.values():

            yield from _walk(
                nested,
            )

    elif isinstance(value, list):

        for nested in value:

            yield from _walk(
                nested,
            )
