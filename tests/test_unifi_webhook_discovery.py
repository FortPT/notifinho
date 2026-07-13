"""Synthetic coverage for the temporary UniFi HTTP capture utility."""

from __future__ import annotations

import json
import http.client
import threading

from pathlib import Path

import pytest

from scripts import capture_unifi_webhook
from scripts.unifi_discovery import classify_unifi


def test_json_http_request_analysis():
    body = json.dumps(
        {
            "application": "UniFi Network",
            "device": {"model": "synthetic", "online": False},
            "events": ["gateway", "switch"],
        }
    ).encode()
    summary = capture_unifi_webhook.analyze_request(
        "POST",
        "/events/network",
        {"Content-Type": "application/json", "Authorization": "secret"},
        body,
    )

    assert summary["method"] == "POST"
    assert summary["body_size"] == len(body)
    assert summary["top_level_json_keys"] == ["application", "device", "events"]
    assert summary["json_shape"] == {
        "application": "string",
        "device": {"model": "string", "online": "boolean"},
        "events": {"item_types": ["str"], "length": 2},
    }
    assert summary["likely_applications"] == ["network"]


def test_non_json_http_request_analysis():
    body = b"UniFi Protect camera health test"
    summary = capture_unifi_webhook.analyze_request(
        "POST",
        "/notify",
        {"Content-Type": "text/plain"},
        body,
    )

    assert summary["content_type"] == "text/plain"
    assert summary["json_shape"] is None
    assert summary["malformed_json"] is False
    assert summary["likely_applications"] == ["protect"]


def test_malformed_json_is_reported_without_body_leakage():
    body = b'{"token":"PrivateToken123456", broken'
    summary = capture_unifi_webhook.analyze_request(
        "POST",
        "/notify",
        {"Content-Type": "application/json"},
        body,
    )

    assert summary["malformed_json"] is True
    assert summary["json_shape"] is None
    assert "PrivateToken" not in capture_unifi_webhook.render_summary(summary)


def test_sensitive_http_values_are_suppressed():
    body = json.dumps(
        {
            "email": "person@sample.invalid",
            "ip": "192.0.2.88",
            "mac": "00:00:5e:00:53:02",
            "url": "https://private.example/hook",
            "uuid": "123e4567-e89b-42d3-a456-426614174000",
            "token": "SyntheticToken123456",
        }
    ).encode()
    summary = capture_unifi_webhook.analyze_request(
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
    rendered = capture_unifi_webhook.render_summary(summary)

    assert summary["header_names"] == [
        "authorization",
        "content-type",
        "cookie",
        "x-internal-host",
    ]
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
        "controller.office.local",
    ):
        assert private_value not in rendered


def test_raw_output_filename_is_safe_and_target_independent(tmp_path):
    destination = capture_unifi_webhook.save_raw_request(
        tmp_path,
        7,
        "POST/../../escape",
        "/../../private-name?token=value",
        {"Content-Type": "text/plain"},
        b"private raw body",
    )

    assert destination.name == "request-000007-request.raw"
    assert destination.parent == tmp_path.resolve()
    assert destination.read_bytes().endswith(b"private raw body")


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("/../../outside", "/<redacted>/<redacted>/<redacted>"),
        ("/events/ABC123456", "/events/<redacted>"),
        ("/events/network", "/events/network"),
        ("/events/Front-Garden", "/events/<redacted>"),
    ],
)
def test_path_traversal_and_identifier_segments_are_redacted(target, expected):
    assert capture_unifi_webhook.path_shape(target) == expected


def test_webhook_summary_is_deterministic():
    arguments = (
        "POST",
        "/hooks/test",
        {"X-Zeta": "private", "Content-Type": "application/json", "X-Alpha": "private"},
        b'{"z": 1, "a": [true, false]}',
    )

    first = capture_unifi_webhook.render_summary(
        capture_unifi_webhook.analyze_request(*arguments)
    )
    second = capture_unifi_webhook.render_summary(
        capture_unifi_webhook.analyze_request(*arguments)
    )

    assert first == second


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("UniFi Network gateway offline", ["network"]),
        ("UniFi Protect camera offline", ["protect"]),
        ("UniFi Drive disk health", ["drive"]),
        ("Ubiquiti UniFi notification", ["generic-unifi"]),
        ("UniFi Network camera event", ["network", "protect"]),
        ("unidentified synthetic product", ["unknown"]),
    ],
)
def test_unifi_marker_classification(text, expected):
    assert classify_unifi([text]) == expected


def test_raw_saving_is_disabled_by_default():
    args = capture_unifi_webhook.parse_args([])

    assert args.host == "127.0.0.1"
    assert args.port == 18080
    assert args.output_dir is None
    assert args.allow_get is False


def test_capture_server_accepts_post_and_optionally_get(capsys):
    server = capture_unifi_webhook.CaptureServer(("127.0.0.1", 0), True, None)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
        connection.request("POST", "/events/network", b"{}", {"Content-Type": "application/json"})
        assert connection.getresponse().status == 204
        connection.request("GET", "/events/network")
        assert connection.getresponse().status == 204
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert capsys.readouterr().out.count('"method":') == 2


def test_capture_server_rejects_get_when_disabled():
    server = capture_unifi_webhook.CaptureServer(("127.0.0.1", 0), False, None)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
        connection.request("GET", "/events/network")
        assert connection.getresponse().status == 405
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_raw_save_failure_still_returns_discovery_success(monkeypatch, tmp_path, capsys):
    def fail_save(*_args, **_kwargs):
        raise OSError("private path detail must not be printed")

    monkeypatch.setattr(capture_unifi_webhook, "save_raw_request", fail_save)
    server = capture_unifi_webhook.CaptureServer(("127.0.0.1", 0), False, tmp_path)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
        connection.request("POST", "/events/network", b"synthetic")
        assert connection.getresponse().status == 204
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    output = capsys.readouterr()
    assert "Raw save failed (OSError)" in output.err
    assert "private path detail" not in output.err


def test_raw_saving_does_not_overwrite_existing_capture(tmp_path):
    first = capture_unifi_webhook.save_raw_request(
        tmp_path, 1, "POST", "/events", {}, b"first"
    )
    second = capture_unifi_webhook.save_raw_request(
        tmp_path, 1, "POST", "/events", {}, b"second"
    )

    assert first.name == "request-000001-post.raw"
    assert second.name == "request-000002-post.raw"
    assert first.read_bytes().endswith(b"first")
    assert second.read_bytes().endswith(b"second")
