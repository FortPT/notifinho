"""Database-backed, secret-safe audit events for v2 platform operations."""

from __future__ import annotations

import json
import re
import time

from dataclasses import dataclass
from typing import Callable

from storage.database import Database
from storage.ownership import Actor
from storage.sanitize import sanitize_text
from storage.validation import normalized_identifier


_SENSITIVE_KEY = re.compile(
    r"(?i)(authorization|cookie|password|secret|token|webhook|api[_-]?key)"
)


@dataclass(frozen=True)
class AuditEvent:
    id: int
    actor_user_id: str | None
    action: str
    resource_type: str
    resource_id: str | None
    outcome: str
    details: dict
    created_at: int


class AuditEventStore:
    def __init__(
        self,
        database: Database,
        *,
        clock: Callable[[], float] = time.time,
    ):
        self.database = database
        self.clock = clock

    def write(
        self,
        actor: Actor | None,
        action: str,
        resource_type: str,
        resource_id: str | None,
        outcome: str,
        details: dict | None = None,
    ) -> int:
        _action, normalized_action = normalized_identifier(
            action,
            "audit action",
            maximum=64,
        )
        _resource, normalized_resource = normalized_identifier(
            resource_type,
            "audit resource type",
            maximum=64,
        )
        _outcome, normalized_outcome = normalized_identifier(
            outcome,
            "audit outcome",
            maximum=32,
        )
        safe_details = self._safe_details(details or {})
        now = int(self.clock())
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO audit_events(
                    actor_user_id, action, resource_type, resource_id,
                    outcome, details_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    actor.user_id if actor else None,
                    normalized_action,
                    normalized_resource,
                    str(resource_id)[:128] if resource_id else None,
                    normalized_outcome,
                    json.dumps(safe_details, sort_keys=True, separators=(",", ":")),
                    now,
                ),
            )
        return int(cursor.lastrowid)

    def list_visible(self, actor: Actor, limit: int = 100) -> list[AuditEvent]:
        bounded = max(1, min(int(limit), 500))
        with self.database.connect() as connection:
            if actor.is_admin:
                rows = connection.execute(
                    "SELECT * FROM audit_events ORDER BY id DESC LIMIT ?",
                    (bounded,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM audit_events
                    WHERE actor_user_id = ? ORDER BY id DESC LIMIT ?
                    """,
                    (actor.user_id, bounded),
                ).fetchall()
        return [self._event(row) for row in rows]

    @classmethod
    def _safe_details(cls, details: dict) -> dict:
        if not isinstance(details, dict):
            raise ValueError("audit details must be an object")
        safe = {}
        for key, value in list(details.items())[:32]:
            label = str(key)[:64]
            if _SENSITIVE_KEY.search(label):
                safe[label] = "<redacted>"
            elif isinstance(value, bool) or value is None:
                safe[label] = value
            elif isinstance(value, (int, float)):
                safe[label] = value
            elif isinstance(value, (list, tuple)):
                safe[label] = [sanitize_text(item)[:128] for item in value[:32]]
            else:
                safe[label] = sanitize_text(value)[:256]
        return safe

    @staticmethod
    def _event(row) -> AuditEvent:
        return AuditEvent(
            id=int(row["id"]),
            actor_user_id=(
                str(row["actor_user_id"])
                if row["actor_user_id"] is not None
                else None
            ),
            action=str(row["action"]),
            resource_type=str(row["resource_type"]),
            resource_id=(
                str(row["resource_id"]) if row["resource_id"] is not None else None
            ),
            outcome=str(row["outcome"]),
            details=json.loads(str(row["details_json"])),
            created_at=int(row["created_at"]),
        )
