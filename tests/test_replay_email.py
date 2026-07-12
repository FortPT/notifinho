"""Unit tests for the local fixture replay utility."""

from __future__ import annotations

import sys

from pathlib import Path

from scripts import replay_email


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "qnap"
    / "storage_warning.eml"
)


def test_replay_defaults_and_fixture_envelope(monkeypatch):

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "replay_email.py",
            str(FIXTURE),
        ],
    )

    args = replay_email.parse_args()
    message = replay_email.load_message(
        args.fixture,
    )
    sender, recipients = replay_email.envelope_addresses(
        message,
    )

    assert args.host == "127.0.0.1"
    assert args.port == 8026
    assert sender.endswith(
        "@synthetic-qnap.invalid"
    )
    assert recipients == [
        "notifinho@receiver.invalid",
    ]
    assert "Storage Pool 1" in str(
        message["Subject"]
    )


def test_replay_returns_nonzero_for_missing_fixture(
    monkeypatch,
    capsys,
):

    missing = (
        Path(__file__).parent
        / "fixtures"
        / "qnap"
        / "missing.eml"
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "replay_email.py",
            str(missing),
        ],
    )

    assert replay_email.main() == 1
    assert "Failure:" in capsys.readouterr().err


def test_replay_empty_refusal_dictionary_is_success(
    monkeypatch,
    capsys,
):

    _set_replay_argv(
        monkeypatch,
    )

    _mock_smtp(
        monkeypatch,
        refused={},
    )

    assert replay_email.main() == 0

    output = capsys.readouterr()

    assert "Success: fixture accepted" in output.out
    assert "Refused recipient" not in output.err


def test_replay_refused_recipient_is_failure(
    monkeypatch,
    capsys,
):

    _set_replay_argv(
        monkeypatch,
    )

    _mock_smtp(
        monkeypatch,
        refused={
            "notifinho@receiver.invalid": (
                550,
                b"Synthetic recipient rejected",
            ),
        },
    )

    assert replay_email.main() == 1

    output = capsys.readouterr()

    assert "Success:" not in output.out
    assert "notifinho@receiver.invalid" in output.err
    assert "SMTP 550: Synthetic recipient rejected" in output.err
    assert "one or more recipients were refused" in output.err


def test_replay_smtp_exception_is_failure(
    monkeypatch,
    capsys,
):

    _set_replay_argv(
        monkeypatch,
    )

    _mock_smtp(
        monkeypatch,
        error=replay_email.smtplib.SMTPException(
            "synthetic SMTP failure"
        ),
    )

    assert replay_email.main() == 1

    output = capsys.readouterr()

    assert "Success:" not in output.out
    assert "Failure: synthetic SMTP failure" in output.err


def _set_replay_argv(
    monkeypatch,
) -> None:

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "replay_email.py",
            str(FIXTURE),
        ],
    )


def _mock_smtp(
    monkeypatch,
    refused=None,
    error: Exception | None = None,
) -> None:

    class SMTP:

        def __init__(
            self,
            host,
            port,
            timeout,
        ):

            self.host = host
            self.port = port
            self.timeout = timeout

        def __enter__(self):

            return self

        def __exit__(
            self,
            exc_type,
            exc,
            traceback,
        ):

            return False

        def send_message(
            self,
            message,
            from_addr,
            to_addrs,
        ):

            if error is not None:

                raise error

            return refused or {}

    monkeypatch.setattr(
        replay_email.smtplib,
        "SMTP",
        SMTP,
    )
