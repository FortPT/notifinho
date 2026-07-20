"""Regression tests for the polished QNAP Teams card."""

from __future__ import annotations

import json

from formatters.teams_qnap import QNAPTeamsFormatter
from models import Notification


def test_qnap_teams_test_message_uses_rich_icons_and_clean_labels():
    notification = Notification(
        source="qnap",
        category="system",
        status="information",
        metadata={
            "nas_name": "NAS-01",
            "application": "Notification Center",
            "category": "system",
            "severity": "Information",
            "event_type": "test_message",
            "event_time": "2026/07/13 09:36:00",
            "message": "[NAS-01] Test Message",
            "source_fields": {
                "This is a test message from NAS": '"NAS-01".',
            },
        },
    )

    card = QNAPTeamsFormatter().format(
        notification,
    )["attachments"][0]["content"]

    serialized = json.dumps(
        card,
        ensure_ascii=False,
    )

    assert card["body"][0]["text"] == "🗄️ ℹ️ NAS-01 • Test Message"
    assert "⚙️ System" in card["body"][1]["text"]
    assert "🧪 [NAS-01] Test Message" in serialized
    assert "ℹ️ Severity" in serialized
    assert "⚙️ Category" in serialized
    assert "📦 Application:" in serialized
    assert "🏷️ Event Type:" in serialized
    assert "test_message" not in serialized
    assert "This Is A Test Message From NAS" not in serialized
