"""
Replay an RFC 5322 email fixture to a local SMTP listener.

The development workflow intentionally uses neither SMTP authentication nor
TLS. The default destination matches Notifinho's development host mapping at
127.0.0.1:8026.
"""

from __future__ import annotations

import argparse
import smtplib
import sys
from email import policy
from email.message import Message
from email.parser import BytesParser
from email.utils import getaddresses, parseaddr
from pathlib import Path


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8026
SMTP_TIMEOUT_SECONDS = 10


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description="Replay an .eml fixture to an SMTP listener.",
    )
    parser.add_argument(
        "fixture",
        type=Path,
        help="Path to the .eml fixture to replay.",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"SMTP host (default: {DEFAULT_HOST}).",
    )
    parser.add_argument(
        "--port",
        default=DEFAULT_PORT,
        type=int,
        help=f"SMTP port (default: {DEFAULT_PORT}).",
    )

    return parser.parse_args()


def load_message(fixture: Path) -> Message:
    """Parse a fixture as bytes using Python's default email policy."""

    with fixture.open("rb") as fixture_file:
        return BytesParser(policy=policy.default).parse(fixture_file)


def envelope_addresses(message: Message) -> tuple[str, list[str]]:
    """Extract SMTP envelope addresses from common message headers."""

    sender_header = str(message.get("From", ""))
    sender = parseaddr(sender_header)[1]

    recipient_headers = message.get_all("To", [])
    recipient_headers += message.get_all("Cc", [])
    recipient_headers += message.get_all("Bcc", [])

    recipients = [
        address
        for _, address in getaddresses(recipient_headers)
        if address
    ]

    if not sender:
        raise ValueError("fixture has no usable From address")

    if not recipients:
        raise ValueError("fixture has no usable To, Cc, or Bcc address")

    return sender, list(dict.fromkeys(recipients))


def print_summary(
    message: Message,
    sender: str,
    recipients: list[str],
    host: str,
    port: int,
) -> None:
    """Print the message and destination selected for replay."""

    subject = str(message.get("Subject", "(no subject)"))

    print(f"Subject: {subject}")
    print(f"Sender: {sender}")
    print(f"Recipient: {', '.join(recipients)}")
    print(f"Target server: {host}:{port}")


def print_refused_recipients(
    refused: dict,
) -> None:
    """Report SMTP recipient refusals without dumping message contents."""

    for address, response in refused.items():

        code = "unknown"
        detail = "no response detail"

        if (
            isinstance(response, tuple)
            and len(response) >= 2
        ):

            code = str(
                response[0],
            )

            raw_detail = response[1]

            if isinstance(raw_detail, bytes):

                detail = raw_detail.decode(
                    "utf-8",
                    errors="replace",
                )

            else:

                detail = str(
                    raw_detail,
                )

        else:

            detail = str(
                response,
            )

        detail = " ".join(
            detail.split()
        )

        print(
            f"Refused recipient: {address} "
            f"(SMTP {code}: {detail})",
            file=sys.stderr,
        )


def main() -> int:
    """Replay one fixture and return a process-friendly status code."""

    args = parse_args()

    try:
        message = load_message(args.fixture)
        sender, recipients = envelope_addresses(message)
        print_summary(
            message,
            sender,
            recipients,
            args.host,
            args.port,
        )

        with smtplib.SMTP(
            args.host,
            args.port,
            timeout=SMTP_TIMEOUT_SECONDS,
        ) as smtp:

            refused = smtp.send_message(
                message,
                from_addr=sender,
                to_addrs=recipients,
            )

        if refused:

            print_refused_recipients(
                refused,
            )

            print(
                "Failure: one or more recipients were refused.",
                file=sys.stderr,
            )

            return 1

    except Exception as exc:
        print(f"Failure: {exc}", file=sys.stderr)
        return 1

    print("Success: fixture accepted by the SMTP server.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
