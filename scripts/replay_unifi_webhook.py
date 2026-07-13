"""Replay only a JSON body and media type from a private raw HTTP capture."""

from __future__ import annotations

import argparse
import json
import sys

from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay a private UniFi JSON capture to a loopback endpoint.",
    )
    parser.add_argument("capture", type=Path, help="local raw HTTP capture")
    parser.add_argument(
        "endpoint",
        help="loopback URL, for example http://127.0.0.1:18080/unifi/network",
    )
    return parser.parse_args(argv)


def load_capture(path: Path) -> tuple[bytes, str]:
    raw = path.read_bytes()
    separator = b"\r\n\r\n" if b"\r\n\r\n" in raw else b"\n\n"
    if separator not in raw:
        raise ValueError("capture has no HTTP header/body separator")
    head, body = raw.split(separator, 1)
    content_type = ""
    for line in head.decode("iso-8859-1", errors="replace").splitlines()[1:]:
        name, marker, value = line.partition(":")
        if marker and name.strip().casefold() == "content-type":
            content_type = value.strip().split(";", 1)[0].casefold()
            break
    if not (
        content_type == "application/json"
        or content_type.startswith("application/")
        and content_type.endswith("+json")
    ):
        raise ValueError("capture content type is not JSON")
    json.loads(body.decode("utf-8"))
    return body, content_type


def validate_endpoint(endpoint: str) -> str:
    parsed = urlsplit(endpoint)
    if parsed.scheme != "http" or parsed.hostname not in {
        "127.0.0.1",
        "::1",
        "localhost",
    }:
        raise ValueError("endpoint must be an HTTP loopback URL")
    if parsed.path not in {"/unifi/network", "/unifi/protect"}:
        raise ValueError("endpoint path must be a supported UniFi webhook path")
    return endpoint


def replay(path: Path, endpoint: str) -> int:
    body, content_type = load_capture(path)
    request = Request(
        validate_endpoint(endpoint),
        data=body,
        headers={"Content-Type": content_type},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        return response.status


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        status = replay(args.capture, args.endpoint)
    except HTTPError as error:
        print(f"Replay failed with HTTP {error.code}", file=sys.stderr)
        return 1
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError, URLError) as error:
        print(f"Replay failed ({type(error).__name__})", file=sys.stderr)
        return 1
    print(f"Replay accepted with HTTP {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
