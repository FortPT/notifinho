"""TrueNAS plain-text, HTML, multipart, grouped, and malformed parser tests."""

from __future__ import annotations

from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path

import pytest

from parsers.truenas import Parser


FIXTURES = Path(__file__).parent / "fixtures" / "truenas"


def parse_fixture(name: str):
    with (FIXTURES / name).open("rb") as fixture:
        return Parser().parse(BytesParser(policy=policy.default).parse(fixture))


def test_plain_text_test_alert():
    notification = parse_fixture("test_alert.eml")
    assert notification.source == "truenas"
    assert notification.metadata["host"] == "SYNTHETIC-TRUENAS"
    assert notification.metadata["event_type"] == "test"
    assert notification.metadata["severity"] == "information"
    assert notification.status == "information"
    assert notification.metadata["parser_confidence"] == "high"


def test_html_pool_alert_and_current_alerts():
    notification = parse_fixture("pool_degraded.eml")
    assert notification.category == "storage"
    assert notification.status == "warning"
    assert notification.metadata["alert_count"] == 2
    assert notification.metadata["event_types"] == ["new", "current"]
    assert all(item["title"] == "Pool health alert" for item in notification.items)


def test_multipart_replication_failure():
    notification = parse_fixture("replication_failure.eml")
    assert notification.metadata["format"] == "multipart"
    assert notification.category == "backup"
    assert notification.status == "failure"
    assert notification.metadata["severity"] == "critical"
    assert notification.metadata["alert_count"] == 1


def test_cleared_recovery_alert():
    notification = parse_fixture("cleared_alert.eml")
    assert notification.status == "success"
    assert notification.metadata["event_type"] == "cleared"
    assert notification.metadata["recovery"] is True
    assert notification.items[0]["severity"] == "normal"


def test_grouped_new_cleared_and_current_alerts():
    notification = parse_fixture("grouped_alerts.eml")
    assert notification.metadata["alert_count"] == 5
    assert notification.metadata["event_types"] == ["new", "cleared", "current"]
    assert notification.status == "failure"
    assert notification.category == "backup"
    assert set(notification.metadata["categories"]) >= {"storage", "backup", "power"}
    assert any(item["recovery"] for item in notification.items)
    assert {item["category"] for item in notification.items} >= {"storage", "backup", "power"}


@pytest.mark.parametrize(
    ("fixture_name", "category", "status", "title_text"),
    [
        ("smart_warning.eml", "storage", "warning", "SMART"),
        ("scrub_failure.eml", "storage", "failure", "Scrub"),
        ("replication_failure.eml", "backup", "failure", "Replication"),
        ("ups_on_battery.eml", "power", "warning", "UPS"),
    ],
)
def test_category_and_state_classification(fixture_name, category, status, title_text):
    notification = parse_fixture(fixture_name)
    assert notification.category == category
    assert notification.status == status
    assert title_text in notification.items[0]["title"]


def test_event_time_is_extracted_when_present():
    notification = parse_fixture("smart_warning.eml")
    assert notification.metadata["event_time"] == "2026-07-12 10:09:00"
    assert notification.start_time == "2026-07-12 10:09:00"


def test_malformed_incomplete_data_does_not_crash():
    notification = parse_fixture("malformed.eml")
    assert notification.source == "truenas"
    assert notification.metadata["parser_confidence"] in {"low", "medium"}
    assert notification.body


def test_empty_message_does_not_crash():
    notification = Parser().parse(EmailMessage())
    assert notification.source == "truenas"
    assert notification.metadata["alert_count"] == 0
    assert notification.status == "information"
