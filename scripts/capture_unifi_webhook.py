"""Temporary standard-library HTTP capture server for UniFi discovery."""

from __future__ import annotations

import argparse
import json
import re
import signal
import sys
import threading

from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

try:
    from scripts.unifi_discovery import (
        REDACTED,
        classify_unifi,
        safe_header_names,
        sanitize_text,
    )
except ModuleNotFoundError:  # Direct execution from the scripts directory.
    from unifi_discovery import (  # type: ignore[no-redef]
        REDACTED,
        classify_unifi,
        safe_header_names,
        sanitize_text,
    )


MAX_BODY_BYTES = 10 * 1024 * 1024
_SAFE_PATH_SEGMENTS = {
    "api",
    "drive",
    "event",
    "events",
    "hook",
    "hooks",
    "network",
    "notification",
    "notifications",
    "notify",
    "protect",
    "unifi",
    "webhook",
    "webhooks",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a temporary sanitized UniFi webhook capture server.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="bind host")
    parser.add_argument("--port", type=int, default=18080, help="bind port")
    parser.add_argument(
        "--allow-get",
        action="store_true",
        help="accept GET as well as POST",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="explicit private directory for raw requests (disabled by default)",
    )
    return parser.parse_args(argv)


def path_shape(target: str) -> str:
    parsed = urlsplit(target)
    segments = []
    for segment in parsed.path.split("/"):
        clean = sanitize_text(segment)
        if segment and clean.casefold() not in _SAFE_PATH_SEGMENTS:
            clean = REDACTED
        segments.append(clean)
    path = "/".join(segments) or "/"
    if parsed.query:
        query = urlencode(
            [
                (sanitize_text(key), REDACTED)
                for key, _ in parse_qsl(parsed.query, keep_blank_values=True)
            ]
        )
        path = f"{path}?{query}"
    return path


def _json_shape(value: object, depth: int = 0) -> object:
    if depth >= 8:
        return "truncated"
    if isinstance(value, dict):
        return {
            sanitize_text(key): _json_shape(item, depth + 1)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, list):
        types = sorted({type(item).__name__ for item in value})
        return {"item_types": types, "length": len(value)}
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    return "string"


def analyze_request(
    method: str,
    target: str,
    headers: Mapping[str, str],
    body: bytes,
) -> dict[str, object]:
    normalized_headers = {str(key).lower(): value for key, value in headers.items()}
    content_type = normalized_headers.get("content-type", "")
    media_type = content_type.split(";", 1)[0].strip().lower() or "unknown"
    json_data: object | None = None
    malformed_json = False
    is_json = media_type == "application/json" or media_type.endswith("+json")

    if is_json:
        try:
            json_data = json.loads(body.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            malformed_json = True

    top_level_keys = []
    if isinstance(json_data, dict):
        top_level_keys = sorted(sanitize_text(key) for key in json_data)

    marker_values: list[object] = [target]
    if json_data is not None:
        marker_values.append(json.dumps(json_data, sort_keys=True))
    else:
        marker_values.append(body.decode("utf-8", errors="replace"))

    return {
        "body_size": len(body),
        "content_type": media_type,
        "header_names": safe_header_names(headers.keys()),
        "json_shape": _json_shape(json_data) if json_data is not None else None,
        "likely_applications": classify_unifi(marker_values),
        "malformed_json": malformed_json,
        "method": method.upper(),
        "path_shape": path_shape(target),
        "top_level_json_keys": top_level_keys,
    }


def render_summary(summary: dict[str, object]) -> str:
    return json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def safe_raw_filename(sequence: int, method: str) -> str:
    candidate = re.sub(r"[^a-z]", "", method.lower())
    safe_method = candidate if candidate in {"delete", "get", "patch", "post", "put"} else "request"
    return f"request-{max(0, sequence):06d}-{safe_method}.raw"


def save_raw_request(
    output_dir: Path,
    sequence: int,
    method: str,
    target: str,
    headers: Mapping[str, str],
    body: bytes,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    root = output_dir.resolve()
    head = [f"{method} {target} HTTP/1.1"]
    head.extend(f"{name}: {value}" for name, value in headers.items())
    raw = ("\r\n".join(head) + "\r\n\r\n").encode("utf-8") + body

    candidate_sequence = max(0, sequence)
    while True:
        destination = (root / safe_raw_filename(candidate_sequence, method)).resolve()
        if destination.parent != root:
            raise ValueError("raw request path escaped output directory")
        try:
            with destination.open("xb") as output:
                output.write(raw)
            return destination
        except FileExistsError:
            candidate_sequence += 1


class CaptureServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, allow_get: bool, output_dir: Path | None):
        super().__init__(address, CaptureHandler)
        self.allow_get = allow_get
        self.output_dir = output_dir
        self._sequence = 0
        self._sequence_lock = threading.Lock()

    def next_sequence(self) -> int:
        with self._sequence_lock:
            self._sequence += 1
            return self._sequence


class CaptureHandler(BaseHTTPRequestHandler):
    server: CaptureServer

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        self._capture()

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        if not self.server.allow_get:
            self.send_error(405, "GET discovery is disabled")
            return
        self._capture()

    def _capture(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length < 0 or length > MAX_BODY_BYTES:
            self.send_error(413, "request body is too large")
            return

        body = self.rfile.read(length)
        headers = dict(self.headers.items())
        summary = analyze_request(self.command, self.path, headers, body)
        sys.stdout.write(render_summary(summary))
        sys.stdout.flush()

        if self.server.output_dir is not None:
            save_raw_request(
                self.server.output_dir,
                self.server.next_sequence(),
                self.command,
                self.path,
                headers,
                body,
            )

        self.send_response(204)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    server = CaptureServer((args.host, args.port), args.allow_get, args.output_dir)

    def shutdown(_signum, _frame) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, shutdown)

    print(
        f"Listening on {sanitize_text(args.host)}:{server.server_port}; "
        f"raw saving={'enabled' if args.output_dir else 'disabled'}",
        flush=True,
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
