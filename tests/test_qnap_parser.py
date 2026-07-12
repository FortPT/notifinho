"""QNAP parser tests using only synthetic email fixtures."""

from __future__ import annotations

from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path

import pytest

from parsers.qnap import Parser as QNAPParser


FIXTURES = Path(__file__).parent / "fixtures" / "qnap"


def parse_fixture(
    name: str,
):

    with (FIXTURES / name).open("rb") as fixture:

        message = BytesParser(
            policy=policy.default,
        ).parse(fixture)

    return QNAPParser().parse(
        message,
    )


def test_plain_text_fixture_parsing():

    notification = parse_fixture(
        "notification_center_test.eml",
    )

    assert notification.source == "qnap"
    assert notification.category == "system"
    assert notification.status == "information"
    assert notification.sender
    assert notification.subject
    assert "synthetic test notification" in notification.body.lower()
    assert notification.metadata["nas_name"] == "SYNTHETIC-QNAP-LAB"
    assert notification.metadata["application"] == "Notification Center"
    assert notification.metadata["event_type"] == "Test Message"
    assert notification.metadata["event_time"] == "2026-07-12 08:00:00"
    assert notification.metadata["fixture_format"] == "plain-text"


def test_html_fixture_parsing():

    notification = parse_fixture(
        "storage_warning.eml",
    )

    assert notification.source == "qnap"
    assert notification.category == "storage"
    assert notification.status == "warning"
    assert "Storage Pool 1 entered" in notification.metadata["message"]
    assert "<table" not in notification.body.lower()
    assert notification.metadata["source_fields"]["raid group"] == (
        "RAID Group 1"
    )
    assert notification.metadata["fixture_format"] == "html"

    source_fields = notification.metadata["source_fields"]

    assert notification.metadata["event_time"] == (
        "2026-07-12 08:30:00"
    )
    assert "2026/07/12 08" not in source_fields
    assert "30:00" not in source_fields.values()


@pytest.mark.parametrize(
    (
        "fixture_name",
        "category",
        "status",
        "event_text",
    ),
    [
        (
            "storage_warning.eml",
            "storage",
            "warning",
            "storage pool warning",
        ),
        (
            "smart_warning.eml",
            "storage",
            "warning",
            "disk smart warning",
        ),
        (
            "failed_login.eml",
            "security",
            "warning",
            "failed login",
        ),
        (
            "hbs_backup_failure.eml",
            "backup",
            "failure",
            "backup job failed",
        ),
        (
            "update_notice.eml",
            "system",
            "information",
            "update available",
        ),
        (
            "ups_power_event.eml",
            "power",
            "warning",
            "ups on battery",
        ),
    ],
)
def test_initial_event_classification(
    fixture_name: str,
    category: str,
    status: str,
    event_text: str,
):

    notification = parse_fixture(
        fixture_name,
    )

    assert notification.category == category
    assert notification.status == status
    assert event_text in notification.metadata["event_type"].lower()
    assert notification.metadata["message"]
    assert notification.metadata["event_time"]
    assert notification.metadata["source_fields"]
    assert notification.metadata["parser_confidence"] in {
        "medium",
        "high",
    }


def test_multipart_fixture_parsing_prefers_plain_body_and_keeps_fields():

    notification = parse_fixture(
        "hbs_backup_failure.eml",
    )

    assert notification.metadata["fixture_format"] == "multipart"
    assert notification.metadata["application"] == "Hybrid Backup Sync"
    assert notification.metadata["source_fields"]["job name"] == (
        "Synthetic Nightly Backup"
    )
    assert "synthetic backup job stopped" in notification.body.lower()


def test_missing_fields_are_tolerated():

    message = EmailMessage()
    message["From"] = "QNAP Notification Center <alerts@qnap.invalid>"
    message["Subject"] = "QNAP notification with missing fields"
    message.set_content(
        "QNAP Notification Center\nMessage: Partial synthetic notice",
    )

    notification = QNAPParser().parse(
        message,
    )

    assert notification.source == "qnap"
    assert notification.category == "system"
    assert notification.status == "information"
    assert notification.title
    assert notification.metadata["message"] == "Partial synthetic notice"
    assert notification.metadata["event_time"] == ""


def test_unknown_labelled_fields_are_preserved():

    message = EmailMessage()
    message["From"] = "QNAP Notification Center <alerts@qnap.invalid>"
    message["Subject"] = "[QNAP] Synthetic notice"
    message.set_content(
        "\n".join(
            [
                "QNAP Notification Center",
                "NAS Name: SYNTHETIC-QNAP-LAB",
                "Severity: Information",
                "Custom Fixture Field: preserved-value",
                "Message: Synthetic notice",
            ]
        )
    )

    notification = QNAPParser().parse(
        message,
    )

    assert notification.metadata["source_fields"]["custom fixture field"] == (
        "preserved-value"
    )


@pytest.mark.parametrize(
    (
        "severity",
        "expected_status",
    ),
    [
        (
            "success",
            "success",
        ),
        (
            "successful",
            "success",
        ),
        (
            "unsuccessful",
            "failure",
        ),
        (
            "not ok",
            "failure",
        ),
        (
            "abnormal",
            "failure",
        ),
        (
            "warning",
            "warning",
        ),
        (
            "alert",
            "warning",
        ),
        (
            "critical",
            "failure",
        ),
        (
            "resolved",
            "success",
        ),
        (
            "information",
            "information",
        ),
    ],
)
def test_status_inference_uses_negative_first_exact_mappings(
    severity: str,
    expected_status: str,
):

    message = EmailMessage()
    message["From"] = "QNAP Notification Center <alerts@qnap.invalid>"
    message["Subject"] = "[QNAP] Synthetic status test"
    message.set_content(
        "NAS Name: SYNTHETIC-QNAP-LAB\n"
        f"Severity: {severity}\n"
        "Message: Synthetic status event",
    )

    notification = QNAPParser().parse(
        message,
    )

    assert notification.status == expected_status
