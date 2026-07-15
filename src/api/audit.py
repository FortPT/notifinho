"""Private-safe append-only API audit events."""

from __future__ import annotations

import json
import os
import threading

from datetime import datetime, timezone
from pathlib import Path


class AuditLog:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def write(self, actor: str, action: str, result: str, source: str = "") -> None:
        safe_path = str(action or "").split("?", 1)[0]
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "principal": str(actor or "anonymous")[:128],
            "path": safe_path[:128],
            "result": str(result)[:64],
            "source": str(source)[:128],
        }
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with self._lock:
                descriptor = os.open(
                    self.path,
                    os.O_APPEND | os.O_CREAT | os.O_WRONLY,
                    0o600,
                )
                with os.fdopen(descriptor, "a", encoding="utf-8") as stream:
                    stream.write(json.dumps(record, separators=(",", ":")) + "\n")
            os.chmod(self.path, 0o600)
        except OSError:
            # Audit failure must not expose request data or crash event delivery.
            return
