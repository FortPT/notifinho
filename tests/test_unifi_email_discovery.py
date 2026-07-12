"""Synthetic coverage for the RFC822 UniFi discovery utility."""

from __future__ import annotations

import json

from email.message import EmailMessage

from scripts import analyze_unifi_email


def _message(subject: str = "UniFi Network gateway disconnected") -> EmailMessage:
    message = EmailMessage()
    message["From"] = "alerts@public-example.invalid"
    message["To"] = "receiver@sample.invalid"
    message["Subject"] = subject
    return message


def test_plain_text_email_analysis():
    message = _message()
    message.set_content("A UniFi Network access point needs attention.")

    summary = analyze_unifi_email.analyze_bytes(message.as_bytes())

    assert summary["content_type"] == "text/plain"
    assert summary["text_plain"] is True
    assert summary["text_html"] is False
    assert summary["likely_applications"] == ["network"]
    assert summary["sender_domain"] == "public-example.invalid"


def test_html_email_analysis():
    message = _message("UniFi Protect device health")
    message.set_content("<html><body>Protect camera offline</body></html>", subtype="html")

    summary = analyze_unifi_email.analyze_bytes(message.as_bytes())

    assert summary["text_html"] is True
    assert summary["text_plain"] is False
    assert summary["likely_applications"] == ["protect"]


def test_multipart_email_and_attachment_analysis():
    message = _message("UniFi Drive backup job")
    message.set_content("UniFi Drive storage notification")
    message.add_alternative("<p>Disk health warning</p>", subtype="html")
    message.add_attachment(
        b"synthetic data",
        maintype="application",
        subtype="octet-stream",
        filename="private-disk-name.bin",
    )

    summary = analyze_unifi_email.analyze_bytes(message.as_bytes())

    assert summary["content_type"] == "multipart/mixed"
    assert summary["multipart_part_types"] == [
        "text/plain",
        "text/html",
        "application/octet-stream",
    ]
    assert summary["text_plain"] is True
    assert summary["text_html"] is True
    assert summary["attachments"] == [
        {
            "content_type": "application/octet-stream",
            "disposition": "attachment",
            "filename_shape": "<redacted>.bin",
            "size": 14,
        }
    ]


def test_malformed_rfc822_input_is_safe():
    summary = analyze_unifi_email.analyze_bytes(
        b"From: broken\r\nContent-Type: multipart/mixed\r\n\r\nno boundary"
    )

    assert summary["malformed"] is True
    assert summary["parse_defects"]
    json.dumps(summary)


def test_email_summary_is_deterministic():
    message = _message()
    message["X-Zeta"] = "one"
    message["X-Alpha"] = "two"
    message.set_content("UniFi Network switch offline")
    data = message.as_bytes()

    first = analyze_unifi_email.render_summary(analyze_unifi_email.analyze_bytes(data))
    second = analyze_unifi_email.render_summary(analyze_unifi_email.analyze_bytes(data))

    assert first == second
    assert first.endswith("\n")


def test_email_private_values_are_redacted():
    message = _message(
        "Protect receiver@sample.invalid 192.0.2.45 00:00:5e:00:53:01 "
        "https://alerts.example/path 123e4567-e89b-42d3-a456-426614174000 "
        "token=TopSecretValue12345 serial=DEVICE999999"
    )
    message.set_content("Camera event")

    rendered = analyze_unifi_email.render_summary(
        analyze_unifi_email.analyze_bytes(message.as_bytes())
    )

    for private_value in (
        "receiver@sample.invalid",
        "192.0.2.45",
        "00:00:5e:00:53:01",
        "https://alerts.example/path",
        "123e4567-e89b-42d3-a456-426614174000",
        "TopSecretValue12345",
        "DEVICE999999",
    ):
        assert private_value not in rendered
    assert "<redacted>" in rendered


def test_subject_shape_hides_human_assigned_device_name():
    message = _message("UniFi Protect camera Front Garden offline")
    message.set_content("Protect camera event")

    summary = analyze_unifi_email.analyze_bytes(message.as_bytes())

    assert summary["subject_shape"] == "unifi protect camera <text> offline"
    assert "Front" not in analyze_unifi_email.render_summary(summary)
    assert "Garden" not in analyze_unifi_email.render_summary(summary)


def test_sensitive_email_header_values_are_suppressed():
    message = _message()
    message["Authorization"] = "Bearer SyntheticSecret123456"
    message["Cookie"] = "session=SyntheticCookie123456"
    message["X-Webhook"] = "https://hooks.example/private"
    message.set_content("Generic UniFi notification")

    rendered = analyze_unifi_email.render_summary(
        analyze_unifi_email.analyze_bytes(message.as_bytes())
    )

    assert "authorization" in rendered
    assert "cookie" in rendered
    assert "x-webhook" in rendered
    assert "SyntheticSecret" not in rendered
    assert "SyntheticCookie" not in rendered
    assert "hooks.example" not in rendered


def test_email_cli_writes_only_explicit_sanitized_output(tmp_path, capsys):
    message = _message("UniFi Network test")
    message.set_content("Synthetic test")
    source = tmp_path / "private.eml"
    source.write_bytes(message.as_bytes())
    before = source.read_bytes()

    assert analyze_unifi_email.main([str(source)]) == 0
    assert list(tmp_path.iterdir()) == [source]
    assert source.read_bytes() == before

    output = tmp_path / "review" / "summary.json"
    assert analyze_unifi_email.main([str(source), "--output", str(output)]) == 0
    assert output.read_text(encoding="utf-8") in capsys.readouterr().out
    assert source.read_bytes() == before
