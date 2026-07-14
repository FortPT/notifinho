"""Sanitize and summarize one private raw Portainer HTTP capture."""

from __future__ import annotations

import argparse
import sys

from pathlib import Path

try:
    from scripts.capture_portainer_webhook import analyze_request, render_summary
except ModuleNotFoundError:  # Direct execution from the scripts directory.
    from capture_portainer_webhook import (  # type: ignore[no-redef]
        analyze_request,
        render_summary,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print a sanitized structural summary of a Portainer HTTP capture.",
    )
    parser.add_argument("capture", type=Path, help="private raw HTTP capture")
    parser.add_argument(
        "--output",
        type=Path,
        help="optional path for the sanitized JSON summary",
    )
    return parser.parse_args(argv)


def load_capture(path: Path) -> tuple[str, str, dict[str, str], bytes]:
    raw = path.read_bytes()
    separator = b"\r\n\r\n" if b"\r\n\r\n" in raw else b"\n\n"
    if separator not in raw:
        raise ValueError("capture has no HTTP header/body separator")
    head, body = raw.split(separator, 1)
    lines = head.decode("iso-8859-1", errors="replace").splitlines()
    if not lines:
        raise ValueError("capture has no request line")

    request_parts = lines[0].split()
    if len(request_parts) < 2:
        raise ValueError("capture request line is malformed")
    method, target = request_parts[:2]

    headers: dict[str, str] = {}
    for line in lines[1:]:
        name, marker, value = line.partition(":")
        if marker:
            headers[name.strip()] = value.strip()
    return method, target, headers, body


def analyze_file(path: Path) -> str:
    return render_summary(analyze_request(*load_capture(path)))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.output is not None and args.capture.resolve() == args.output.resolve():
            raise ValueError("output must not replace the original capture")
        rendered = analyze_file(args.capture)
        sys.stdout.write(rendered)
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
    except (OSError, ValueError) as error:
        print(
            f"Failure: unable to analyze requested capture ({type(error).__name__})",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
