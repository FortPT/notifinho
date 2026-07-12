"""Grafana source detection and precedence tests."""

from __future__ import annotations

import logging

from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path

import pytest

from dispatcher import Dispatcher


FIXTURES = Path(__file__).parent / "fixtures" / "grafana"


def load_fixture(name: str):

    with (FIXTURES / name).open("rb") as fixture:

        return BytesParser(
            policy=policy.default,
        ).parse(fixture)


@pytest.mark.parametrize(
    "fixture_name",
    [
        "test_notification.eml",
        "alert_firing.eml",
        "alert_resolved.eml",
        "alert_pending.eml",
        "alert_no_data.eml",
        "datasource_error.eml",
        "multiple_alerts.eml",
    ],
)
def test_all_synthetic_fixtures_are_detected(
    fixture_name: str,
):

    assert Dispatcher().parse(
        load_fixture(fixture_name)
    ).source == "grafana"


def test_detection_is_case_insensitive_and_logs(caplog):

    message = EmailMessage()
    message["From"] = "gRaFaNa AlErTiNg <alerts@grafana.invalid>"
    message["Subject"] = "[FiRiNg] Synthetic alert"
    message.set_content(
        "ALERT RULE: Synthetic Rule\nSTATE: FIRING",
    )

    with caplog.at_level(
        logging.INFO,
        logger="notifinho.tests",
    ):

        notification = Dispatcher().parse(
            message,
        )

    assert notification.source == "grafana"
    assert "Detected Grafana email" in caplog.messages


def test_multipart_html_only_markers_are_detected():

    message = EmailMessage()
    message["From"] = "Synthetic Alerts <alerts@example.invalid>"
    message["Subject"] = "[FIRING] Synthetic alert"
    message.set_content(
        "A sparse plain-text alternative.",
    )
    message.add_alternative(
        "<h2>Grafana Alerting</h2>"
        "<p>Alert rule: Synthetic Rule</p>"
        "<p>Grafana folder: Synthetic Folder</p>"
        "<p>StartsAt: 2026-07-12 12:00:00</p>",
        subtype="html",
    )

    assert Dispatcher().parse(message).source == "grafana"


def test_attachment_grafana_text_does_not_trigger_detection():

    message = EmailMessage()
    message["From"] = "Generic Appliance <alerts@example.invalid>"
    message["Subject"] = "Generic appliance notice"
    message.set_content(
        "A generic notification body.",
    )
    message.add_attachment(
        "Grafana Alerting\nAlert rule: Hidden attachment rule\n"
        "Grafana folder: Hidden attachment folder",
        subtype="plain",
        filename="synthetic-grafana.txt",
    )

    assert Dispatcher().parse(message).source == "generic"


@pytest.mark.parametrize(
    (
        "subject",
        "body",
    ),
    [
        (
            "Generic monitoring alert",
            "Alert: Synthetic CPU warning\nState: Firing",
        ),
        (
            "[FIRING] Competing vendor alert",
            "Alert name: Synthetic Alert\nAlert rule: Synthetic Rule\n"
            "Labels: service=synthetic\nValues: A=1",
        ),
        (
            "Generic dashboard notification",
            "Dashboard: Synthetic Dashboard\nPanel: Synthetic Panel",
        ),
    ],
)
def test_weak_or_competing_alerts_are_not_detected(
    subject: str,
    body: str,
):

    message = EmailMessage()
    message["From"] = "Competing Monitor <alerts@competitor.invalid>"
    message["Subject"] = subject
    message.set_content(body)

    assert Dispatcher().parse(message).source == "generic"


def test_grafana_sender_with_sparse_body_is_detected():

    message = EmailMessage()
    message["From"] = "Grafana <alerts@grafana.invalid>"
    message["Subject"] = "Synthetic custom template"
    message.set_content(
        "Sparse synthetic contact-point content.",
    )

    assert Dispatcher().parse(message).source == "grafana"


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
        (
            "QNAP Notification Center <alerts@qnap.invalid>",
            "qnap",
        ),
    ],
)
def test_existing_source_precedence_is_unchanged(
    sender: str,
    expected_source: str,
):

    message = EmailMessage()
    message["From"] = sender
    message["Subject"] = "Existing source regression"
    message.set_content(
        "<h2>Grafana Alerting</h2>"
        "<p>Alert rule: Synthetic Rule</p>"
        "<p>Grafana folder: Synthetic Folder</p>",
        subtype="html",
    )

    assert Dispatcher().parse(message).source == expected_source
