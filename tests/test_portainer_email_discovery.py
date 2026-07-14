"""Synthetic coverage for private-safe Portainer email discovery."""

from __future__ import annotations

import json

from email.message import EmailMessage

from scripts import analyze_portainer_email


def _message(subject: str = "Portainer alert environment unavailable") -> EmailMessage:
    message = EmailMessage()
    message["From"] = "alerts@private-example.invalid"
    message["To"] = "receiver@sample.invalid"
    message["Subject"] = subject
    return message


def test_plain_text_email_analysis():
    message = _message()
    message.set_content("Portainer container alert severity critical.")

    summary = analyze_portainer_email.analyze_bytes(message.as_bytes())

    assert summary["content_type"] == "text/plain"
    assert summary["text_plain"] is True
    assert summary["text_html"] is False
    assert summary["likely_payloads"] == ["portainer"]
    assert summary["sender_present"] is True


def test_html_email_analysis():
    message = _message("Portainer alert resolved")
    message.set_content(
        "<html><body>Portainer service recovered</body></html>", subtype="html"
    )

    summary = analyze_portainer_email.analyze_bytes(message.as_bytes())

    assert summary["text_html"] is True
    assert summary["text_plain"] is False
    assert summary["likely_payloads"] == ["portainer"]


def test_multipart_and_attachment_metadata_are_private_safe():
    message = _message("Portainer critical alert")
    message.set_content("Portainer stack alert")
    message.add_alternative("<p>Environment unavailable</p>", subtype="html")
    message.add_attachment(
        b"synthetic data",
        maintype="application",
        subtype="octet-stream",
        filename="private-environment-name.bin",
    )

    summary = analyze_portainer_email.analyze_bytes(message.as_bytes())

    assert summary["content_type"] == "multipart/mixed"
    assert summary["multipart_part_types"] == [
        "text/plain",
        "text/html",
        "application/octet-stream",
    ]
    assert summary["attachments"] == [
        {
            "content_type": "application/octet-stream",
            "disposition": "attachment",
            "filename_shape": "<redacted>.bin",
            "size": 14,
        }
    ]


def test_email_private_values_are_not_rendered():
    message = _message(
        "Portainer Production-Cluster receiver@sample.invalid 192.0.2.45 "
        "00:00:5e:00:53:01 https://alerts.example/path "
        "123e4567-e89b-42d3-a456-426614174000 token=TopSecretValue12345"
    )
    message.set_content("Portainer container alert")

    rendered = analyze_portainer_email.render_summary(
        analyze_portainer_email.analyze_bytes(message.as_bytes())
    )

    for private_value in (
        "Production",
        "receiver@sample.invalid",
        "192.0.2.45",
        "00:00:5e:00:53:01",
        "alerts.example",
        "123e4567",
        "TopSecretValue",
        "private-example.invalid",
    ):
        assert private_value not in rendered
    assert "<redacted>" in rendered


def test_subject_shape_preserves_only_known_vocabulary():
    message = _message("Portainer critical alert Production Cluster unavailable")
    message.set_content("Portainer event")

    summary = analyze_portainer_email.analyze_bytes(message.as_bytes())

    assert summary["subject_shape"] == (
        "portainer critical alert <text> unavailable"
    )


def test_malformed_rfc822_input_is_safe():
    summary = analyze_portainer_email.analyze_bytes(
        b"From: broken\r\nContent-Type: multipart/mixed\r\n\r\nno boundary"
    )

    assert summary["malformed"] is True
    assert summary["parse_defects"]
    json.dumps(summary)


def test_email_cli_writes_only_explicit_sanitized_output(tmp_path, capsys):
    message = _message("Portainer test notification")
    message.set_content("Synthetic Portainer test")
    source = tmp_path / "private.eml"
    source.write_bytes(message.as_bytes())
    before = source.read_bytes()

    assert analyze_portainer_email.main([str(source)]) == 0
    assert list(tmp_path.iterdir()) == [source]
    assert source.read_bytes() == before

    output = tmp_path / "review" / "summary.json"
    assert analyze_portainer_email.main(
        [str(source), "--output", str(output)]
    ) == 0
    assert output.read_text(encoding="utf-8") in capsys.readouterr().out
    assert source.read_bytes() == before


def test_email_cli_refuses_to_replace_original(tmp_path, capsys):
    message = _message("Portainer test")
    message.set_content("Synthetic test")
    source = tmp_path / "private.eml"
    source.write_bytes(message.as_bytes())
    before = source.read_bytes()

    assert analyze_portainer_email.main(
        [str(source), "--output", str(source)]
    ) == 1
    assert source.read_bytes() == before
    assert "unable to read or write requested path" in capsys.readouterr().err
