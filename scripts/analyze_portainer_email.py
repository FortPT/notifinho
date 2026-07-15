"""Sanitize and summarize one private Portainer RFC822 message."""

from __future__ import annotations

import argparse
import json
import re
import sys

from email import policy
from email.message import Message
from email.parser import BytesParser
from pathlib import Path

try:
    from scripts.portainer_discovery import (
        REDACTED,
        classify_portainer,
        safe_header_names,
        sanitize_text,
    )
except ModuleNotFoundError:  # Direct execution from the scripts directory.
    from portainer_discovery import (  # type: ignore[no-redef]
        REDACTED,
        classify_portainer,
        safe_header_names,
        sanitize_text,
    )


_SAFE_SUBJECT_WORDS = {
    "active",
    "alert",
    "alerting",
    "container",
    "critical",
    "endpoint",
    "environment",
    "error",
    "failed",
    "firing",
    "healthy",
    "inactive",
    "information",
    "instance",
    "notification",
    "pending",
    "portainer",
    "recovered",
    "resolved",
    "rule",
    "service",
    "severity",
    "stack",
    "test",
    "unavailable",
    "unhealthy",
    "warning",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print a sanitized structural summary of one Portainer .eml file.",
    )
    parser.add_argument("eml", type=Path, help="private RFC822 .eml file")
    parser.add_argument(
        "--output",
        type=Path,
        help="optional path for the sanitized JSON summary",
    )
    return parser.parse_args(argv)


def _payload_text(part: Message) -> str:
    try:
        return part.get_content()
    except (LookupError, TypeError, UnicodeError):
        payload = part.get_payload(decode=True) or b""
        return payload.decode("utf-8", errors="replace")


def _filename_shape(part: Message) -> str | None:
    filename = part.get_filename()
    if not filename:
        return None
    suffix = Path(filename).suffix.lower()
    if not suffix or len(suffix) > 12 or not suffix[1:].isalnum():
        suffix = ""
    return f"{REDACTED}{suffix}"


def subject_shape(subject: object) -> str:
    """Preserve known alert vocabulary while hiding arbitrary labels."""

    sanitized = sanitize_text(subject)
    tokens = re.findall(r"<redacted>|[A-Za-z]+|\d+|[^\w\s]", sanitized)
    shaped: list[str] = []
    for token in tokens:
        if token == REDACTED:
            replacement = REDACTED
        elif token.casefold() in _SAFE_SUBJECT_WORDS:
            replacement = token.casefold()
        elif token.isalpha() or token.isdigit():
            replacement = "<text>"
        else:
            replacement = token
        if (
            not shaped
            or replacement != shaped[-1]
            or replacement not in {"<text>", REDACTED}
        ):
            shaped.append(replacement)
    return " ".join(shaped)


def analyze_bytes(data: bytes) -> dict[str, object]:
    """Parse bytes defensively and return only sanitized structural data."""

    defects: list[str] = []
    try:
        message = BytesParser(policy=policy.default).parsebytes(data)
        defects = sorted({type(defect).__name__ for defect in message.defects})
    except Exception as error:  # The utility must survive arbitrary captures.
        return {
            "attachments": [],
            "content_type": "application/octet-stream",
            "header_names": [],
            "likely_payloads": ["unknown"],
            "malformed": True,
            "multipart_part_types": [],
            "parse_defects": [type(error).__name__],
            "sender_present": False,
            "subject_shape": "",
            "text_html": False,
            "text_plain": False,
        }

    part_types: list[str] = []
    attachments: list[dict[str, object]] = []
    marker_values: list[object] = [message.get("Subject", "")]
    has_plain = False
    has_html = False

    for part in message.walk():
        if part is message and not message.is_multipart():
            pass
        elif not part.is_multipart():
            part_types.append(part.get_content_type().lower())

        content_type = part.get_content_type().lower()
        disposition = part.get_content_disposition()

        if content_type == "text/plain":
            has_plain = True
            marker_values.append(_payload_text(part))
        elif content_type == "text/html":
            has_html = True
            marker_values.append(_payload_text(part))

        if disposition == "attachment" or part.get_filename():
            payload = part.get_payload(decode=True) or b""
            attachments.append(
                {
                    "content_type": content_type,
                    "disposition": disposition or "unspecified",
                    "filename_shape": _filename_shape(part),
                    "size": len(payload),
                }
            )

    return {
        "attachments": attachments,
        "content_type": message.get_content_type().lower(),
        "header_names": safe_header_names(message.keys()),
        "likely_payloads": classify_portainer(marker_values),
        "malformed": bool(defects),
        "multipart_part_types": part_types if message.is_multipart() else [],
        "parse_defects": defects,
        "sender_present": bool(str(message.get("From", "")).strip()),
        "subject_shape": subject_shape(message.get("Subject", "")),
        "text_html": has_html,
        "text_plain": has_plain,
    }


def render_summary(summary: dict[str, object]) -> str:
    return json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.output is not None and args.eml.resolve() == args.output.resolve():
            raise ValueError("output must not replace the original message")
        data = args.eml.read_bytes()
        rendered = render_summary(analyze_bytes(data))
        sys.stdout.write(rendered)
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
    except (OSError, ValueError) as error:
        print(
            f"Failure: unable to read or write requested path ({type(error).__name__})",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
