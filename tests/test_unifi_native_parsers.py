"""Synthetic parser and strong-detection tests for native UniFi sources."""

from __future__ import annotations

import copy
import json

from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path

import pytest

from dispatcher import Dispatcher
from formatters.discord_unifi import (
    UniFiDriveDiscordFormatter,
    UniFiProtectDiscordFormatter,
)
from formatters.teams_unifi import (
    UniFiDriveTeamsFormatter,
    UniFiProtectTeamsFormatter,
)
from formatters.unifi import format_protect_event_time
from parsers.unifi_drive import Parser as DriveParser
from parsers.unifi_network import Parser as NetworkParser
from parsers.unifi_protect import Parser as ProtectParser


FIXTURES = Path(__file__).parent / "fixtures" / "unifi"


def network_payload() -> dict:
    return json.loads((FIXTURES / "network" / "client_disconnected.json").read_text())


def protect_payload() -> dict:
    return json.loads((FIXTURES / "protect" / "motion.json").read_text())


def drive_message(name: str):
    with (FIXTURES / "drive" / name).open("rb") as fixture:
        return BytesParser(policy=policy.default).parse(fixture)


def test_network_discovered_client_disconnect_envelope():
    notification = NetworkParser().parse(network_payload())

    assert notification.source == "unifi_network"
    assert notification.title == "WiFi Client Disconnected"
    assert notification.status == "information"
    assert notification.metadata["vendor_severity"] == 2
    assert notification.metadata["client_display_name"] == "SYNTHETIC-CLIENT"
    assert notification.metadata["wifi_channel"] == "36"
    assert notification.metadata["last_device_name"] == "SYNTHETIC-AP"
    assert notification.duration == "5m 30s"


def test_network_missing_optional_parameters_and_unknown_event():
    payload = network_payload()
    payload["name"] = "Synthetic Unknown Network Event"
    payload["parameters"] = {"UNIFIcategory": "Synthetic"}

    notification = NetworkParser().parse(payload)

    assert notification.source == "unifi_network"
    assert notification.title == "Synthetic Unknown Network Event"
    assert notification.metadata["client_ip"] == ""


@pytest.mark.parametrize(
    "payload",
    [
        {"app": "network", "parameters": []},
        {"name": "network", "message": "ordinary JSON"},
        {"app": "network", "parameters": {}, "name": "event"},
    ],
)
def test_network_malformed_or_false_positive_json_is_rejected(payload):
    assert NetworkParser.is_envelope(payload) is False
    assert Dispatcher().parse_webhook("network", payload) is None


@pytest.mark.parametrize(
    ("vendor_severity", "expected_status", "expected_severity"),
    [
        (2, "information", "information"),
        (3, "warning", "warning"),
        (4, "failure", "critical"),
    ],
)
def test_network_numeric_severity_is_preserved_and_normalized(
    vendor_severity, expected_status, expected_severity
):
    payload = network_payload()
    payload["severity"] = vendor_severity
    notification = NetworkParser().parse(payload)

    assert notification.status == expected_status
    assert notification.metadata["severity"] == expected_severity
    assert notification.metadata["vendor_severity"] == vendor_severity


def test_protect_discovered_motion_envelope():
    notification = ProtectParser().parse(protect_payload())

    assert notification.source == "unifi_protect"
    assert notification.metadata["condition_source"] == "motion"
    assert notification.metadata["condition_operator"] == "is"
    assert notification.metadata["trigger_key"] == "motion"
    assert notification.metadata["trigger_device"] == "SYNTHETIC-CAMERA-02"
    assert notification.metadata["configured_source_count"] == 2
    assert notification.metadata["event_link"].startswith("https://protect.example/")


def test_protect_multiple_triggers_and_malformed_members():
    payload = protect_payload()
    payload["alarm"]["triggers"].extend(
        [
            None,
            "bad-member",
            {
                "device": "SYNTHETIC-CAMERA-03",
                "eventId": "synthetic-event-0002",
                "key": "person",
                "timestamp": 1767323050,
            },
        ]
    )

    notification = ProtectParser().parse(payload)

    assert notification.metadata["trigger_count"] == 2
    assert len(notification.items) == 2
    assert notification.items[1]["key"] == "person"


def test_protect_empty_conditions_sources_and_triggers():
    payload = protect_payload()
    payload["alarm"].update(conditions=[], sources=[], triggers=[])

    notification = ProtectParser().parse(payload)

    assert notification.metadata["condition_source"] == ""
    assert notification.metadata["configured_source_count"] == 0
    assert notification.metadata["trigger_count"] == 0
    assert notification.title == "Synthetic motion alarm"


def test_protect_seconds_and_milliseconds_timestamps_match():
    seconds = protect_payload()
    milliseconds = copy.deepcopy(seconds)
    seconds["alarm"]["triggers"][0]["timestamp"] = 1767323045
    milliseconds["alarm"]["triggers"][0]["timestamp"] = 1767323045000

    first = ProtectParser().parse(seconds)
    second = ProtectParser().parse(milliseconds)

    assert first.start_time == "1767323045"
    assert second.start_time == "1767323045000"
    assert format_protect_event_time(first.start_time) == (
        format_protect_event_time(second.start_time)
    )


@pytest.mark.parametrize("link", ["javascript:alert(1)", "/relative/event", "not a URL"])
def test_protect_invalid_links_are_omitted(link):
    payload = protect_payload()
    payload["alarm"]["eventLocalLink"] = link
    assert ProtectParser().parse(payload).metadata["event_link"] == ""


def test_protect_opaque_trigger_device_is_not_logged_at_info(caplog):
    payload = protect_payload()
    payload["alarm"]["triggers"][0]["device"] = "00:00:5e:00:53:42"
    caplog.set_level("INFO", logger="notifinho.tests")

    notification = Dispatcher().parse_webhook("protect", payload)

    assert notification.metadata["trigger_device"] == "00:00:5e:00:53:42"
    assert "Detected UniFi Protect webhook" in caplog.text
    assert "00:00:5e:00:53:42" not in caplog.text


@pytest.mark.parametrize(
    "payload",
    [
        {"alarm": "motion", "alarm_id": "x", "timestamp": 1},
        {"alarm": {"name": "motion"}, "alarm_id": "x", "timestamp": 1},
        {"alarm": {"triggers": {}}, "alarm_id": "x", "timestamp": 1},
    ],
)
def test_protect_false_positive_nested_json_is_rejected(payload):
    assert ProtectParser.is_envelope(payload) is False


@pytest.mark.parametrize(
    ("fixture_name", "status", "category", "state"),
    [
        ("backup_partial.eml", "warning", "backup", "partially completed"),
        ("backup_failed.eml", "failure", "backup", "failed"),
        ("backup_completed.eml", "success", "backup", "completed"),
        ("storage_pool.eml", "failure", "storage", "suspended"),
    ],
)
def test_drive_provisional_event_classification(fixture_name, status, category, state):
    message = drive_message(fixture_name)
    assert DriveParser.is_message(message)
    notification = DriveParser().parse(message)

    assert notification.source == "unifi_drive"
    assert notification.status == status
    assert notification.category == category
    assert notification.metadata["event_state"] == state
    assert notification.metadata["system"] == "SYNTHETIC-DRIVE"


def test_drive_plain_text_is_preferred_over_html():
    message = EmailMessage()
    message["From"] = '"UniFi OS, SYNTHETIC-DRIVE" <alerts@notifications.ui.com>'
    message["Subject"] = "Backup Task Partially Completed"
    message.set_content(
        "UniFi Drive\nThe backup task PLAIN-TASK on SYNTHETIC-DRIVE was completed partially."
    )
    message.add_alternative(
        "<p>The backup task HTML-TASK on WRONG-SYSTEM was completed partially.</p>",
        subtype="html",
    )

    notification = DriveParser().parse(message)

    assert notification.job_name == "PLAIN-TASK"
    assert "HTML-TASK" not in notification.body
    assert notification.metadata["format"] == "plain"


def test_drive_html_only_removes_style_script_footer_and_inline_images():
    message = EmailMessage()
    message["From"] = '"UniFi OS, SYNTHETIC-DRIVE" <alerts@notifications.ui.com>'
    message["Subject"] = "Backup Task Partially Completed"
    message.set_content(
        """
        <html><head><style>.secret { display:none }</style></head><body>
        <script>trackingToken = 'synthetic-secret'</script>
        <img src='cid:brand-one'><img src='cid:brand-two'>
        <h1>Backup Task Partially Completed</h1>
        <p>The backup task HTML-TASK on SYNTHETIC-DRIVE was completed partially.</p>
        <a href='https://drive.example/manage/synthetic'>Manage Backup Task</a>
        <footer>Copyright Synthetic Postal Address</footer>
        </body></html>
        """,
        subtype="html",
    )
    message.add_related(b"png-one", maintype="image", subtype="png", cid="brand-one")
    message.add_related(b"png-two", maintype="image", subtype="png", cid="brand-two")

    notification = DriveParser().parse(message)

    assert notification.job_name == "HTML-TASK"
    assert notification.metadata["format"] == "html"
    assert notification.metadata["action_link"] == "https://drive.example/manage/synthetic"
    assert "trackingToken" not in notification.body
    assert "Copyright" not in notification.body
    assert len(notification.items) == 0


def _visible_card_text(value) -> list[str]:
    visible = []
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in {"description", "text", "title", "value"} and isinstance(
                nested,
                str,
            ):
                visible.append(nested)
            elif key != "url":
                visible.extend(_visible_card_text(nested))
    elif isinstance(value, list):
        for nested in value:
            visible.extend(_visible_card_text(nested))
    return visible


def test_protect_readable_trigger_device_remains_in_body_and_visible_cards():
    payload = protect_payload()
    payload["alarm"]["triggers"][0]["device"] = "Front Entrance Camera"

    notification = ProtectParser().parse(payload)
    discord = UniFiProtectDiscordFormatter().format(notification)
    teams = UniFiProtectTeamsFormatter().format(notification)

    assert notification.body == "Motion detected by Front Entrance Camera"
    assert "Front Entrance Camera" in "\n".join(_visible_card_text(discord))
    assert "Front Entrance Camera" in "\n".join(_visible_card_text(teams))


@pytest.mark.parametrize(
    "device_value",
    [
        "FAKE_MAC",
        "00:00:5e:00:53:43",
        "123e4567-e89b-42d3-a456-426614174000",
        "A1B2C3D4E5F60708",
    ],
)
def test_protect_private_trigger_device_is_absent_from_body_and_visible_cards(
    device_value,
):
    payload = protect_payload()
    payload["alarm"]["triggers"][0]["device"] = device_value

    notification = ProtectParser().parse(payload)
    discord = UniFiProtectDiscordFormatter().format(notification)
    teams = UniFiProtectTeamsFormatter().format(notification)
    visible = "\n".join(
        _visible_card_text(discord) + _visible_card_text(teams)
    )

    assert notification.body == "Motion detected"
    assert not notification.body.endswith(" by")
    assert device_value not in notification.body
    assert device_value not in visible
    assert notification.metadata["trigger_device"] == device_value


def test_drive_body_removes_action_url_signature_and_footer_but_keeps_operations():
    action_link = (
        "https://console.example.invalid/manage/"
        "opaque-console-identifier-0123456789"
    )
    message = EmailMessage()
    message["From"] = '"UniFi OS, SYNTHETIC-DRIVE" <alerts@notifications.ui.com>'
    message["Subject"] = "Backup Task Partially Completed"
    message.set_content(
        "\n".join(
            [
                "UniFi Drive",
                "The backup task SYNTHETIC-BACKUP on SYNTHETIC-DRIVE was completed partially.",
                "Please check the details in UniFi Drive > Settings > Remote backup to resolve the issue.",
                f"Manage Backup Task: {action_link}",
                action_link,
                "Regards,",
                "The Ubiquiti team",
                "Contact support in the Support Center",
                "Unsubscribe from these notifications",
                "Copyright Synthetic Postal Address",
            ]
        )
    )

    notification = DriveParser().parse(message)
    discord = UniFiDriveDiscordFormatter().format(notification)
    teams = UniFiDriveTeamsFormatter().format(notification)
    visible_discord = "\n".join(_visible_card_text(discord))
    visible_teams = "\n".join(_visible_card_text(teams))

    assert notification.metadata["action_link"] == action_link
    assert action_link not in notification.body
    assert "Regards" not in notification.body
    assert "The Ubiquiti team" not in notification.body
    assert "Unsubscribe" not in notification.body
    assert "Contact support" not in notification.body
    assert "Copyright" not in notification.body
    assert "was completed partially" in notification.body
    assert "UniFi Drive > Settings > Remote backup" in notification.body
    assert action_link not in visible_discord
    assert action_link not in visible_teams
    assert discord["embeds"][0]["url"] == action_link
    teams_card = teams["attachments"][0]["content"]
    assert teams_card["actions"] == [
        {
            "type": "Action.OpenUrl",
            "title": "Manage Backup Task",
            "url": action_link,
        }
    ]


def test_drive_sender_domain_alone_is_not_sufficient():
    message = EmailMessage()
    message["From"] = "Unrelated <alerts@notifications.ui.com>"
    message["Subject"] = "Ordinary account message"
    message.set_content("A generic unrelated notification.")

    assert DriveParser.is_message(message) is False
    assert Dispatcher().parse(message).source == "generic"


def test_unknown_drive_event_still_parses_generically_when_identity_is_strong():
    message = EmailMessage()
    message["From"] = '"UniFi OS, SYNTHETIC-DRIVE" <alerts@notifications.ui.com>'
    message["Subject"] = "Remote Backup Policy Notice"
    message.set_content(
        "UniFi Drive remote backup task policy notice. Check Remote backup settings."
    )

    assert DriveParser.is_message(message)
    notification = DriveParser().parse(message)
    assert notification.source == "unifi_drive"
    assert notification.category == "generic"
    assert notification.metadata["event_state"] == "unknown"


def test_drive_dispatcher_detection_preserves_existing_sender_precedence():
    message = drive_message("backup_partial.eml")
    assert Dispatcher().parse(message).source == "unifi_drive"

    message.replace_header("From", "Zabbix <alerts@zabbix.invalid>")
    assert Dispatcher().parse(message).source == "zabbix"


def test_drive_detection_logs_do_not_expose_system_or_task_names(caplog):
    caplog.set_level("INFO", logger="notifinho.tests")
    Dispatcher().parse(drive_message("backup_partial.eml"))
    rendered = caplog.text
    assert "Detected UniFi Drive email" in rendered
    assert "SYNTHETIC-DRIVE" not in rendered
    assert "SYNTHETIC-BACKUP" not in rendered
