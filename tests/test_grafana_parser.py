"""Grafana parser tests using synthetic fixtures."""

from __future__ import annotations

from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path

import pytest

from parsers.grafana import Parser as GrafanaParser


FIXTURES = Path(__file__).parent / "fixtures" / "grafana"


def parse_fixture(name: str):

    with (FIXTURES / name).open("rb") as fixture:

        message = BytesParser(
            policy=policy.default,
        ).parse(fixture)

    return GrafanaParser().parse(message)


def test_firing_alert_parsing():

    notification = parse_fixture("alert_firing.eml")
    metadata = notification.metadata

    assert notification.source == "grafana"
    assert notification.category == "alerting"
    assert notification.status == "failure"
    assert notification.start_time == "2026-07-12 10:15:00"
    assert metadata["alert_name"] == "Synthetic API Latency"
    assert metadata["alert_rule"] == "Synthetic API Latency Rule"
    assert metadata["folder"] == "Synthetic Platform"
    assert metadata["dashboard"] == "Synthetic Service Overview"
    assert metadata["panel"] == "Synthetic Latency Panel"
    assert metadata["datasource"] == "Synthetic Metrics Source"
    assert metadata["labels"]
    assert metadata["values"]
    assert metadata["dashboard_url"].endswith(".invalid/d/synthetic-service")
    assert metadata["fixture_format"] == "multipart"


def test_resolved_alert_parsing():

    notification = parse_fixture("alert_resolved.eml")

    assert notification.category == "alerting"
    assert notification.status == "success"
    assert notification.end_time == "2026-07-12 10:30:00"
    assert notification.metadata["state"] == "Resolved"
    assert notification.metadata["ends_at"] == "2026-07-12 10:30:00"
    assert notification.metadata["fixture_format"] == "html"


@pytest.mark.parametrize(
    (
        "fixture_name",
        "category",
        "status",
        "state",
    ),
    [
        (
            "test_notification.eml",
            "system",
            "information",
            "Test",
        ),
        (
            "alert_pending.eml",
            "alerting",
            "warning",
            "Pending",
        ),
        (
            "alert_no_data.eml",
            "alerting",
            "warning",
            "No Data",
        ),
        (
            "datasource_error.eml",
            "datasource",
            "failure",
            "Error",
        ),
    ],
)
def test_initial_state_classification(
    fixture_name: str,
    category: str,
    status: str,
    state: str,
):

    notification = parse_fixture(fixture_name)

    assert notification.category == category
    assert notification.status == status
    assert notification.metadata["state"] == state
    assert notification.metadata["message"]
    assert notification.metadata["source_fields"]
    assert notification.metadata["parser_confidence"] in {
        "medium",
        "high",
    }


def test_multiple_alert_notification_parsing():

    notification = parse_fixture("multiple_alerts.eml")

    assert notification.status == "failure"
    assert notification.metadata["alert_count"] == 2
    assert notification.metadata["source_fields"]["alert 1"] == (
        "Synthetic Cache Saturation"
    )
    assert notification.metadata["source_fields"]["alert 2"] == (
        "Synthetic Worker Failure"
    )


def test_missing_and_malformed_fields_are_tolerated():

    message = EmailMessage()
    message["From"] = "Grafana <alerts@grafana.invalid>"
    message["Subject"] = "Sparse synthetic Grafana notice"
    message.set_content(
        b"\xff\xfe\x00",
        maintype="application",
        subtype="octet-stream",
    )

    notification = GrafanaParser().parse(message)

    assert notification.source == "grafana"
    assert notification.category == "generic"
    assert notification.status == "information"
    assert notification.title
    assert notification.metadata["event_time"] == ""
    assert notification.metadata["source_fields"] == {}


def test_unknown_labelled_fields_are_preserved():

    message = EmailMessage()
    message["From"] = "Grafana Alerting <alerts@grafana.invalid>"
    message["Subject"] = "[FIRING] Synthetic custom field"
    message.set_content(
        "Grafana Alerting\n"
        "State: Firing\n"
        "Alert rule: Synthetic Rule\n"
        "Custom Template Field: preserved-value\n"
        "Message: Synthetic event",
    )

    notification = GrafanaParser().parse(message)

    assert notification.metadata["source_fields"]["custom template field"] == (
        "preserved-value"
    )


@pytest.mark.parametrize(
    (
        "state",
        "expected_status",
    ),
    [
        ("Firing", "failure"),
        ("Error", "failure"),
        ("Critical", "failure"),
        ("Unsuccessful", "failure"),
        ("Not OK", "failure"),
        ("Abnormal", "failure"),
        ("Not Resolved", "failure"),
        ("Warning", "warning"),
        ("Pending", "warning"),
        ("No Data", "warning"),
        ("Resolved", "success"),
        ("Normal", "success"),
        ("Successful", "success"),
        ("Completed", "success"),
        ("Test", "information"),
        ("Information", "information"),
    ],
)
def test_negative_first_status_inference(
    state: str,
    expected_status: str,
):

    message = EmailMessage()
    message["From"] = "Grafana Alerting <alerts@grafana.invalid>"
    message["Subject"] = "Synthetic state inference"
    message.set_content(
        "Grafana Alerting\n"
        f"State: {state}\n"
        "Alert rule: Synthetic State Rule\n"
        "Message: Synthetic state event",
    )

    assert GrafanaParser().parse(message).status == expected_status
