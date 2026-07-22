"""Privilege-free scheduled backups to local and host-mounted storage."""

from __future__ import annotations

import sqlite3
import threading
import time

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from storage.backups import StateBackupStore
from storage.ownership import Actor


class BackupScheduler:
    def __init__(self, database, configuration, *, clock=time.time, interval=30):
        self.database = database
        self.configuration = configuration
        self.clock = clock
        self.interval = max(5, int(interval))
        self.store = StateBackupStore(database)
        self._stop = threading.Event()
        self._thread = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run,
            name="notifinho-backups",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._thread = None

    def run_due(self, now: float | None = None) -> dict | None:
        reload_configuration = getattr(self.configuration, "reload", None)
        if callable(reload_configuration):
            try:
                reload_configuration()
            except Exception:
                return None
        values = self.configuration.get("platform", "backups", default={}) or {}
        if not isinstance(values, dict):
            return None
        schedule = str(values.get("schedule") or "disabled").casefold()
        if schedule == "disabled":
            return None
        try:
            zone = ZoneInfo(
                str(
                    self.configuration.get(
                        "presentation", "timezone", default="Europe/Lisbon"
                    )
                    or "Europe/Lisbon"
                )
            )
        except (ValueError, ZoneInfoNotFoundError):
            zone = ZoneInfo("UTC")
        current = datetime.fromtimestamp(self.clock() if now is None else now, zone)
        hour, minute = (int(part) for part in str(values.get("time") or "02:00").split(":"))
        if (current.hour, current.minute) < (hour, minute):
            return None
        if schedule == "weekly" and current.weekday() != int(values.get("weekday", 0)):
            return None
        if schedule == "monthly" and current.day != int(values.get("day", 1)):
            return None
        period = self._period(schedule, current)
        started_at = int(self.clock() if now is None else now)
        try:
            with self.database.transaction() as connection:
                connection.execute(
                    "INSERT INTO backup_schedule_runs(period_key, started_at) VALUES (?, ?)",
                    (period, started_at),
                )
        except sqlite3.IntegrityError:
            return None
        actor = self._administrator()
        if actor is None:
            self._finish(period, "skipped_no_administrator", None, None)
            return {"period": period, "outcome": "skipped_no_administrator"}
        try:
            backup = self.store.create(actor)
            external_path = None
            if values.get("external_enabled") is True:
                external_path = str(
                    self.store.mirror(actor, backup.id, str(values.get("external_path") or ""))
                )
            self._finish(period, "success", backup.id, external_path)
            return {
                "period": period,
                "outcome": "success",
                "backup_id": backup.id,
                "external_path": external_path,
            }
        except Exception:
            self._finish(period, "failed", None, None)
            return {"period": period, "outcome": "failed"}

    def last_run(self) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM backup_schedule_runs ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row is not None else None

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            self.run_due()

    def _administrator(self) -> Actor | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT id FROM users
                WHERE role = 'admin' AND enabled = 1
                ORDER BY created_at, id LIMIT 1
                """
            ).fetchone()
        return Actor(str(row["id"]), "admin") if row is not None else None

    def _finish(self, period, outcome, backup_id, external_path) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE backup_schedule_runs
                SET completed_at = ?, outcome = ?, backup_id = ?, external_path = ?
                WHERE period_key = ?
                """,
                (int(self.clock()), outcome, backup_id, external_path, period),
            )

    @staticmethod
    def _period(schedule: str, current: datetime) -> str:
        if schedule == "daily":
            return f"daily:{current:%Y-%m-%d}"
        if schedule == "weekly":
            year, week, _weekday = current.isocalendar()
            return f"weekly:{year}-W{week:02d}"
        return f"monthly:{current:%Y-%m}"
