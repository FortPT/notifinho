"""Private-safe UniFi webhook replay utility tests."""

from __future__ import annotations

import json

import pytest

from scripts import replay_unifi_webhook


def raw_capture(body: bytes, extra_headers: bytes = b"") -> bytes:
    return (
        b"POST /unifi/network HTTP/1.1\r\n"
        b"Host: private-host.example.invalid\r\n"
        b"Authorization: Bearer synthetic-secret\r\n"
        b"Cookie: session=synthetic-cookie\r\n"
        b"X-Notifinho-Token: synthetic-token\r\n"
        b"Content-Type: application/json\r\n"
        + extra_headers
        + b"\r\n"
        + body
    )


def test_replay_sends_only_json_body_and_content_type(monkeypatch, tmp_path):
    body = json.dumps({"app": "network", "synthetic": True}).encode()
    capture = tmp_path / "capture.raw"
    capture.write_bytes(raw_capture(body))
    captured = {}

    class Response:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def fake_urlopen(request, timeout):
        captured.update(
            url=request.full_url,
            data=request.data,
            headers=dict(request.header_items()),
            timeout=timeout,
        )
        return Response()

    monkeypatch.setattr(replay_unifi_webhook, "urlopen", fake_urlopen)
    status = replay_unifi_webhook.replay(
        capture,
        "http://127.0.0.1:18080/unifi/network",
    )

    assert status == 204
    assert captured["data"] == body
    assert captured["headers"] == {"Content-type": "application/json"}
    assert "Authorization" not in captured["headers"]
    assert "Cookie" not in captured["headers"]
    assert "X-notifinho-token" not in captured["headers"]


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://127.0.0.1/unifi/network",
        "http://example.invalid/unifi/network",
        "http://127.0.0.1/unknown",
    ],
)
def test_replay_refuses_non_loopback_or_unknown_endpoints(endpoint):
    with pytest.raises(ValueError):
        replay_unifi_webhook.validate_endpoint(endpoint)


def test_replay_rejects_non_json_capture(tmp_path):
    capture = tmp_path / "capture.raw"
    capture.write_bytes(
        b"POST / HTTP/1.1\r\nContent-Type: text/plain\r\n\r\nprivate"
    )
    with pytest.raises(ValueError):
        replay_unifi_webhook.load_capture(capture)


def test_replay_cli_error_does_not_print_private_path(tmp_path, capsys):
    private_name = tmp_path / "private-camera-name.raw"
    assert replay_unifi_webhook.main(
        [str(private_name), "http://127.0.0.1:18080/unifi/network"]
    ) == 1
    assert "private-camera-name" not in capsys.readouterr().err
