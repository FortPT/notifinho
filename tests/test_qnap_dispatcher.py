"""QNAP dispatcher detection and existing-source precedence tests."""

from __future__ import annotations

import logging

from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path

import pytest

from dispatcher import Dispatcher


FIXTURES = Path(__file__).parent / "fixtures" / "qnap"


def load_fixture(
    name: str,
):

    with (FIXTURES / name).open("rb") as fixture:

        return BytesParser(
            policy=policy.default,
        ).parse(fixture)


@pytest.mark.parametrize(
    "fixture_name",
    [
        "notification_center_test.eml",
        "failed_login.eml",
        "storage_warning.eml",
        "smart_warning.eml",
        "hbs_backup_failure.eml",
        "update_notice.eml",
        "ups_power_event.eml",
    ],
)
def test_dispatcher_detects_qnap_fixtures(
    fixture_name: str,
):

    notification = Dispatcher().parse(
        load_fixture(fixture_name),
    )

    assert notification.source == "qnap"


def test_qnap_detection_is_case_insensitive_and_logs(caplog):

    message = EmailMessage()
    message["From"] = "qNaP Alerts <alerts@synthetic-qnap.invalid>"
    message["Subject"] = "[qUtS HeRo] STORAGE WARNING"
    message.set_content(
        "Notification Center\nNAS NAME: SYNTHETIC-NAS\n"
        "SEVERITY: Warning\nMESSAGE: Synthetic event",
    )

    with caplog.at_level(
        logging.INFO,
        logger="notifinho.tests",
    ):

        notification = Dispatcher().parse(
            message,
        )

    assert notification.source == "qnap"
    assert "Detected QNAP email" in caplog.messages


def test_structured_qnap_message_can_use_custom_sender():

    message = EmailMessage()
    message["From"] = "Appliance Alerts <alerts@example.invalid>"
    message["Subject"] = "[QuTS hero] Notification Center warning"
    message.set_content(
        "QNAP Notification Center\n"
        "NAS Name: SYNTHETIC-QNAP-HERO\n"
        "Severity: Warning\n"
        "Category: Storage\n"
        "Message: Synthetic storage event",
    )

    assert Dispatcher().parse(message).source == "qnap"


def test_detection_inspects_all_multipart_text_alternatives():

    message = EmailMessage()
    message["From"] = "Appliance Alerts <alerts@example.invalid>"
    message["Subject"] = "[QuTS hero] Synthetic warning"
    message.set_content(
        "A minimal plain-text alternative.",
    )
    message.add_alternative(
        "<h2>QNAP Notification Center</h2>"
        "<p>NAS Name: SYNTHETIC-QNAP-HERO</p>"
        "<p>Severity: Warning</p>"
        "<p>Category: Storage</p>"
        "<p>Message: Synthetic event</p>",
        subtype="html",
    )

    assert Dispatcher().parse(message).source == "qnap"


def test_attachment_text_does_not_trigger_qnap_detection():

    message = EmailMessage()
    message["From"] = "Generic Appliance <alerts@example.invalid>"
    message["Subject"] = "Generic appliance notice"
    message.set_content(
        "A generic system notification without vendor markers.",
    )
    message.add_attachment(
        "QNAP Notification Center\n"
        "NAS Name: SYNTHETIC-QNAP-LAB\n"
        "Severity: Warning\n"
        "Category: Storage\n"
        "Message: Attachment content must be ignored",
        subtype="plain",
        filename="synthetic-note.txt",
    )

    assert Dispatcher().parse(message).source == "generic"


def test_qnap_sender_with_sparse_body_detects_qnap():

    message = EmailMessage()
    message["From"] = "QNAP Alerts <alerts@qnap.invalid>"
    message["Subject"] = "Synthetic appliance notice"
    message.set_content(
        "A sparse synthetic alert body.",
    )

    assert Dispatcher().parse(message).source == "qnap"


def test_lone_generic_nas_keyword_does_not_detect_qnap():

    message = EmailMessage()
    message["From"] = "Generic Appliance <alerts@example.invalid>"
    message["Subject"] = "NAS storage warning"
    message.set_content(
        "A generic NAS reported that its storage is nearly full.",
    )

    assert Dispatcher().parse(message).source == "generic"


def test_generic_notification_center_fields_do_not_detect_qnap():

    message = EmailMessage()
    message["From"] = "Generic Appliance <alerts@competitor.invalid>"
    message["Subject"] = "[Notification Center] NAS warning"
    message.set_content(
        "Notification Center\n"
        "NAS Name: SYNTHETIC-COMPETITOR\n"
        "Severity: Warning\n"
        "Category: Storage\n"
        "Message: Generic synthetic event",
    )

    assert Dispatcher().parse(message).source == "generic"


def test_qnap_specific_application_and_structured_fields_detect_qnap():

    message = EmailMessage()
    message["From"] = "Appliance Alerts <alerts@example.invalid>"
    message["Subject"] = "Hybrid Backup Sync job failed"
    message.set_content(
        "NAS Name: SYNTHETIC-QNAP-LAB\n"
        "Severity: Error\n"
        "Category: Backup\n"
        "App Name: Hybrid Backup Sync\n"
        "Event Type: Backup Job Failed\n"
        "Message: Synthetic backup failure",
    )

    assert Dispatcher().parse(message).source == "qnap"


@pytest.mark.parametrize(
    (
        "sender",
        "expected_source",
    ),
    [
        (
            "Xen Orchestra <alerts@xo.invalid>",
            "xo",
        ),
        (
            "Zabbix <alerts@zabbix.invalid>",
            "zabbix",
        ),
    ],
)
def test_existing_source_selection_keeps_precedence(
    sender: str,
    expected_source: str,
):

    message = EmailMessage()
    message["From"] = sender
    message["Subject"] = "Existing source regression check"
    message.set_content(
        "<html><body><p>QNAP Notification Center</p>"
        "<p>NAS Name: SYNTHETIC-NAS</p>"
        "<p>Severity: Warning</p></body></html>",
        subtype="html",
    )

    notification = Dispatcher().parse(
        message,
    )

    assert notification.source == expected_source
