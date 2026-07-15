"""Synthetic coverage for private-safe Portainer webhook discovery."""

from __future__ import annotations

import http.client
import json
import threading

from pathlib import Path

import pytest

from scripts import analyze_portainer_webhook, capture_portainer_webhook
from scripts.portainer_discovery import classify_portainer


def test_portainer_json_request_analysis():
    body = json.dumps(
        {
            "receiver": "webhook",
            "status": "firing",
            "alerts": [{"labels": {"source": "Portainer"}}],
            "commonLabels": {"severity": "critical"},
        }
    ).encode()
    summary = capture_portainer_webhook.analyze_request(
        "POST",
        "/portainer/alerts",
        {"Content-Type": "application/json", "Authorization": "secret"},
        body,
    )

    assert summary["method"] == "POST"
    assert summary["body_size"] == len(body)
    assert summary["top_level_json_keys"] == [
        "alerts",
        "commonLabels",
        "receiver",
        "status",
    ]
    assert summary["json_shape"] == {
        "alerts": {"item_types": ["dict"], "length": 1},
        "commonLabels": {"severity": "string"},
        "receiver": "string",
        "status": "string",
    }
    assert summary["likely_payloads"] == [
        "portainer",
        "alertmanager-compatible",
    ]
    assert summary["first_alert_shape"] == {"labels": {"source": "string"}}
    assert summary["portainer_enums"] == {
        "alert_statuses": ["<redacted>"],
        "severity": "critical",
        "top_status": "firing",
    }


def test_non_json_request_analysis_is_private_safe():
    body = b"Portainer alert name container unavailable severity critical"
    summary = capture_portainer_webhook.analyze_request(
        "POST",
        "/notify",
        {"Content-Type": "text/plain"},
        body,
    )

    assert summary["content_type"] == "text/plain"
    assert summary["json_shape"] is None
    assert summary["malformed_json"] is False
    assert summary["likely_payloads"] == ["portainer"]
    assert body.decode() not in capture_portainer_webhook.render_summary(summary)


def test_malformed_json_is_reported_without_body_leakage():
    body = b'{"token":"PrivateToken123456", broken'
    summary = capture_portainer_webhook.analyze_request(
        "POST",
        "/portainer/alerts",
        {"Content-Type": "application/json"},
        body,
    )

    rendered = capture_portainer_webhook.render_summary(summary)
    assert summary["malformed_json"] is True
    assert summary["json_shape"] is None
    assert "PrivateToken" not in rendered


def test_sensitive_http_values_are_suppressed():
    body = json.dumps(
        {
            "email": "person@sample.invalid",
            "ip": "192.0.2.88",
            "mac": "00:00:5e:00:53:02",
            "url": "https://private.example/hook",
            "uuid": "123e4567-e89b-42d3-a456-426614174000",
            "token": "SyntheticToken123456",
            "environment_id": "EnvironmentSecret123456",
        }
    ).encode()
    summary = capture_portainer_webhook.analyze_request(
        "POST",
        "/api/123e4567-e89b-42d3-a456-426614174000?token=secret",
        {
            "Content-Type": "application/json",
            "Authorization": "Bearer SyntheticAuthorization123456",
            "Cookie": "session=SyntheticCookie123456",
            "X-Internal-Host": "controller.office.local",
        },
        body,
    )
    rendered = capture_portainer_webhook.render_summary(summary)

    assert summary["path_shape"] == "/api/<redacted>?token=%3Credacted%3E"
    for private_value in (
        "person@sample.invalid",
        "192.0.2.88",
        "00:00:5e:00:53:02",
        "private.example",
        "123e4567",
        "SyntheticToken",
        "SyntheticAuthorization",
        "SyntheticCookie",
        "EnvironmentSecret",
        "controller.office.local",
    ):
        assert private_value not in rendered


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("/../../outside", "/<redacted>/<redacted>/<redacted>"),
        ("/portainer/alerts", "/portainer/alerts"),
        ("/alerts/Production", "/alerts/<redacted>"),
    ],
)
def test_identifier_path_segments_are_redacted(target, expected):
    assert capture_portainer_webhook.path_shape(target) == expected


def test_raw_saving_is_disabled_by_default():
    args = capture_portainer_webhook.parse_args([])

    assert args.host == "127.0.0.1"
    assert args.port == 18083
    assert args.output_dir is None
    assert args.allow_get is False


def test_capture_server_accepts_post_and_rejects_get(capsys):
    server = capture_portainer_webhook.CaptureServer(("127.0.0.1", 0), False, None)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        connection = http.client.HTTPConnection(
            "127.0.0.1", server.server_port, timeout=2
        )
        connection.request(
            "POST",
            "/portainer/alerts",
            b"{}",
            {"Content-Type": "application/json"},
        )
        assert connection.getresponse().status == 204
        connection.request("GET", "/portainer/alerts")
        assert connection.getresponse().status == 405
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert capsys.readouterr().out.count('"method":') == 1


def test_raw_saving_never_overwrites_existing_capture(tmp_path):
    first = capture_portainer_webhook.save_raw_request(
        tmp_path, 1, "POST", "/portainer/alerts", {}, b"first"
    )
    second = capture_portainer_webhook.save_raw_request(
        tmp_path, 1, "POST", "/portainer/alerts", {}, b"second"
    )

    assert first.name == "request-000001-post.raw"
    assert second.name == "request-000002-post.raw"
    assert first.read_bytes().endswith(b"first")
    assert second.read_bytes().endswith(b"second")


def test_offline_analyzer_outputs_only_sanitized_structure(tmp_path, capsys):
    capture = tmp_path / "private.raw"
    capture.write_bytes(
        b"POST /portainer/alerts HTTP/1.1\r\n"
        b"Content-Type: application/json\r\n"
        b"Authorization: Bearer PrivateSecret123456\r\n\r\n"
        b'{"source":"Portainer","token":"PrivateToken123456"}'
    )
    output = tmp_path / "review" / "summary.json"

    assert analyze_portainer_webhook.main(
        [str(capture), "--output", str(output)]
    ) == 0
    rendered = output.read_text(encoding="utf-8")
    assert rendered in capsys.readouterr().out
    assert "PrivateSecret" not in rendered
    assert "PrivateToken" not in rendered
    assert '"source": "string"' in rendered


def test_offline_analyzer_refuses_to_replace_original(tmp_path, capsys):
    capture = tmp_path / "private.raw"
    capture.write_bytes(b"POST /portainer/alerts HTTP/1.1\r\n\r\n{}")
    before = capture.read_bytes()

    assert analyze_portainer_webhook.main(
        [str(capture), "--output", str(capture)]
    ) == 1
    assert capture.read_bytes() == before
    assert "unable to analyze requested capture" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Portainer environment unavailable", ["portainer"]),
        (
            "Alert Name test Severity critical Instance one Started At now",
            ["alerting-envelope"],
        ),
        (
            'Alertmanager {"status":"firing","alerts":[]}',
            ["alertmanager-compatible"],
        ),
        ("unidentified synthetic product", ["unknown"]),
    ],
)
def test_portainer_marker_classification(text, expected):
    assert classify_portainer([text]) == expected
