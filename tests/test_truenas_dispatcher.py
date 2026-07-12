"""TrueNAS source detection and precedence tests."""

from __future__ import annotations

from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path

import pytest

from dispatcher import Dispatcher


FIXTURES = Path(__file__).parent / "fixtures" / "truenas"


def load_fixture(name: str):
    with (FIXTURES / name).open("rb") as fixture:
        return BytesParser(policy=policy.default).parse(fixture)


@pytest.mark.parametrize(
    "fixture_name",
    [
        "test_alert.eml",
        "pool_degraded.eml",
        "smart_warning.eml",
        "scrub_failure.eml",
        "replication_failure.eml",
        "ups_on_battery.eml",
        "cleared_alert.eml",
        "grouped_alerts.eml",
        "malformed.eml",
    ],
)
def test_all_synthetic_fixtures_are_detected(fixture_name: str):
    assert Dispatcher().parse(load_fixture(fixture_name)).source == "truenas"


def test_detection_is_case_insensitive():
    message = EmailMessage()
    message["From"] = "tRuEnAs Alerts <alerts@example.invalid>"
    message["Subject"] = "aLeRtS"
    message.set_content("tRuEnAs @ SYNTHETIC-TRUENAS\nNeW AlErT:\n* Pool warning")
    assert Dispatcher().parse(message).source == "truenas"


@pytest.mark.parametrize(
    ("subject", "body"),
    [
        ("Alerts", "A generic alert without product identity."),
        ("Routine notice", "The word TrueNAS appears without alert structure."),
        ("Alerts", "Current alerts are available in another system."),
    ],
)
def test_weak_markers_are_rejected(subject: str, body: str):
    message = EmailMessage()
    message["From"] = "Generic Service <alerts@example.invalid>"
    message["Subject"] = subject
    message.set_content(body)
    assert Dispatcher().parse(message).source == "generic"


def test_attachment_only_marker_is_rejected():
    message = EmailMessage()
    message["From"] = "Generic Service <alerts@example.invalid>"
    message["Subject"] = "Alerts"
    message.set_content("Generic visible message")
    message.add_attachment(
        "TrueNAS @ SYNTHETIC-TRUENAS\nNew alert:\n* Pool failed",
        subtype="plain",
        filename="synthetic.txt",
    )
    assert Dispatcher().parse(message).source == "generic"


def test_recipient_alias_is_not_a_vendor_header_signal():
    message = EmailMessage()
    message["From"] = "Generic Service <alerts@example.invalid>"
    message["To"] = "truenas@example.invalid"
    message["Subject"] = "Alerts"
    message.set_content("Generic visible message")
    assert Dispatcher().parse(message).source == "generic"


@pytest.mark.parametrize(
    "body",
    [
        "Generic visible text\n-----Original Message-----\nTrueNAS @ SYNTHETIC-TRUENAS\nNew alert:\n* Pool failed",
        "Generic visible text\n> TrueNAS @ SYNTHETIC-TRUENAS\n> New alert:\n> * Pool failed",
    ],
)
def test_quoted_or_forwarded_marker_is_rejected(body: str):
    message = EmailMessage()
    message["From"] = "Generic Service <alerts@example.invalid>"
    message["Subject"] = "Alerts"
    message.set_content(body)
    assert Dispatcher().parse(message).source == "generic"


def test_html_blockquote_marker_is_rejected():
    message = EmailMessage()
    message["From"] = "Generic Service <alerts@example.invalid>"
    message["Subject"] = "Alerts"
    message.set_content(
        "<p>Generic visible text</p><blockquote>TrueNAS @ SYNTHETIC-TRUENAS<br>New alert:<ul><li>Pool failed</li></ul></blockquote>",
        subtype="html",
    )
    assert Dispatcher().parse(message).source == "generic"


@pytest.mark.parametrize(
    ("sender", "subject", "body", "expected"),
    [
        ("Xen Orchestra <alerts@xo.invalid>", "Report", "TrueNAS @ SYNTHETIC-TRUENAS\nNew alert:\n* Pool failed", "xo"),
        ("Zabbix <alerts@zabbix.invalid>", "Problem", "TrueNAS @ SYNTHETIC-TRUENAS\nNew alert:\n* Pool failed", "zabbix"),
        ("Proxmox <alerts@proxmox.invalid>", "Backup", "TrueNAS @ SYNTHETIC-TRUENAS\nNew alert:\n* Pool failed", "proxmox"),
        ("QNAP Notification Center <alerts@qnap.invalid>", "QNAP warning", "TrueNAS @ SYNTHETIC-TRUENAS\nNew alert:\n* Pool failed", "qnap"),
        ("Grafana <alerts@grafana.invalid>", "[FIRING] Alert", "TrueNAS @ SYNTHETIC-TRUENAS\nNew alert:\n* Pool failed", "grafana"),
    ],
)
def test_existing_integrations_keep_precedence(sender, subject, body, expected):
    message = EmailMessage()
    message["From"] = sender
    message["Subject"] = subject
    message.set_content(body)
    assert Dispatcher().parse(message).source == expected


def test_generic_fallback_regression():
    message = EmailMessage()
    message["From"] = "Generic Service <alerts@example.invalid>"
    message["Subject"] = "Ordinary notification"
    message.set_content("Ordinary synthetic content")
    assert Dispatcher().parse(message).source == "generic"
