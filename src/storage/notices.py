"""Administrator announcements and lifecycle-bound system notices."""

from __future__ import annotations

import time
import uuid

from dataclasses import dataclass
from typing import Callable

from storage.database import Database
from storage.ownership import Actor
from storage.sanitize import sanitize_text


NOTICE_STATUSES = {"information", "warning", "severe"}
NOTICE_KINDS = {"announcement", "system_error", "update"}


@dataclass(frozen=True)
class Notice:
    id: str
    name: str
    message: str
    status: str
    kind: str
    persistent: bool
    created_at: int


class NoticeStore:
    """Store announcements and per-user dismissals without client state."""

    def __init__(self, database: Database, *, clock: Callable[[], float] = time.time):
        self.database = database
        self.clock = clock

    def ensure_defaults(self) -> None:
        self.sync_system(
            "welcome-operations",
            "Notification operations",
            "Connect applications, build focused routes, and keep delivery behaviour visible from one private workspace.",
            status="information",
            kind="announcement",
            persistent=False,
            active=True,
        )
        self.sync_system(
            "mounted-configuration",
            "Mounted configuration",
            "WebUI and external config.yaml changes are validated and synchronized through the same configuration authority.",
            status="information",
            kind="announcement",
            persistent=False,
            active=True,
        )

    def create(self, actor: Actor, name: str, message: str, status: str) -> Notice:
        self._require_admin(actor)
        display = self._text(name, 120, "notice name")
        body = self._text(message, 2000, "notice message")
        normalized_status = str(status or "").strip().casefold()
        if normalized_status not in NOTICE_STATUSES:
            raise ValueError("notice status is invalid")
        notice_id = uuid.uuid4().hex
        now = int(self.clock())
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO notices(
                    id, created_by_user_id, name, message, status, kind,
                    persistent, created_at
                ) VALUES (?, ?, ?, ?, ?, 'announcement', 0, ?)
                """,
                (notice_id, actor.user_id, display, body, normalized_status, now),
            )
        return self.get(notice_id)

    def list_visible(self, actor: Actor) -> list[Notice]:
        self.ensure_defaults()
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT notices.* FROM notices
                LEFT JOIN notice_dismissals
                  ON notice_dismissals.notice_id = notices.id
                 AND notice_dismissals.user_id = ?
                WHERE notices.resolved_at IS NULL
                  AND (notices.persistent = 1 OR notice_dismissals.notice_id IS NULL)
                ORDER BY
                  CASE notices.status
                    WHEN 'severe' THEN 0
                    WHEN 'warning' THEN 1
                    ELSE 2
                  END,
                  notices.created_at DESC,
                  notices.id
                """,
                (actor.user_id,),
            ).fetchall()
        return [self._notice(row) for row in rows]

    def dismiss(self, actor: Actor, notice_id: str) -> None:
        notice = self.get(notice_id)
        if notice.persistent:
            raise PermissionError("system errors and updates remain until resolved")
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO notice_dismissals(notice_id, user_id, dismissed_at)
                VALUES (?, ?, ?)
                ON CONFLICT(notice_id, user_id) DO UPDATE
                SET dismissed_at = excluded.dismissed_at
                """,
                (notice.id, actor.user_id, int(self.clock())),
            )

    def sync_system(
        self,
        key: str,
        name: str,
        message: str,
        *,
        status: str,
        kind: str,
        persistent: bool,
        active: bool,
    ) -> None:
        system_key = self._text(key, 120, "system notice key")
        if status not in NOTICE_STATUSES or kind not in NOTICE_KINDS:
            raise ValueError("system notice classification is invalid")
        now = int(self.clock())
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT id, resolved_at FROM notices WHERE system_key = ?",
                (system_key,),
            ).fetchone()
            if active:
                if row is None:
                    connection.execute(
                        """
                        INSERT INTO notices(
                            id, name, message, status, kind, system_key,
                            persistent, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(system_key) DO UPDATE SET
                            name = excluded.name,
                            message = excluded.message,
                            status = excluded.status,
                            kind = excluded.kind,
                            persistent = excluded.persistent,
                            resolved_at = NULL
                        """,
                        (
                            uuid.uuid4().hex,
                            self._text(name, 120, "notice name"),
                            self._text(message, 2000, "notice message"),
                            status,
                            kind,
                            system_key,
                            1 if persistent else 0,
                            now,
                        ),
                    )
                else:
                    connection.execute(
                        """
                        UPDATE notices
                        SET name = ?, message = ?, status = ?, kind = ?,
                            persistent = ?, resolved_at = NULL,
                            created_at = CASE WHEN resolved_at IS NULL THEN created_at ELSE ? END
                        WHERE system_key = ?
                        """,
                        (
                            self._text(name, 120, "notice name"),
                            self._text(message, 2000, "notice message"),
                            status,
                            kind,
                            1 if persistent else 0,
                            now,
                            system_key,
                        ),
                    )
            elif row is not None and row["resolved_at"] is None:
                connection.execute(
                    "UPDATE notices SET resolved_at = ? WHERE system_key = ?",
                    (now, system_key),
                )

    def get(self, notice_id: str) -> Notice:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM notices WHERE id = ? AND resolved_at IS NULL",
                (str(notice_id),),
            ).fetchone()
        if row is None:
            raise KeyError("notice not found")
        return self._notice(row)

    @staticmethod
    def _notice(row) -> Notice:
        return Notice(
            id=str(row["id"]),
            name=str(row["name"]),
            message=str(row["message"]),
            status=str(row["status"]),
            kind=str(row["kind"]),
            persistent=bool(row["persistent"]),
            created_at=int(row["created_at"]),
        )

    @staticmethod
    def _text(value, maximum: int, label: str) -> str:
        text = sanitize_text(value).strip()
        if not text or len(text) > maximum:
            raise ValueError(f"{label} must contain 1 to {maximum} characters")
        return text

    @staticmethod
    def _require_admin(actor: Actor) -> None:
        if not actor.is_admin:
            raise PermissionError("administrator access is required")
