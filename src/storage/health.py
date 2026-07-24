"""Safe operational checks shown beside the platform audit trail."""

from __future__ import annotations

import time
from pathlib import Path


class HealthCheckService:
    def __init__(self, database, configuration_sync, *, clock=time.time):
        self.database = database
        self.configuration_sync = configuration_sync
        self.clock = clock

    def run(self) -> list[dict]:
        checks = [self._database(), self._configuration()]
        checks.extend(self._routing())
        checks.append(self._backup_target())
        checks.append(self._deliveries())
        return checks

    def _database(self):
        try:
            with self.database.connect() as connection:
                result = str(connection.execute("PRAGMA quick_check").fetchone()[0])
            return self._check("database", result == "ok", "SQLite integrity", result)
        except Exception:
            return self._check("database", False, "SQLite integrity", "check failed")

    def _configuration(self):
        if self.configuration_sync is None:
            return self._check("configuration", True, "Configuration", "legacy mode")
        status = self.configuration_sync.synchronize()
        if status.ready and status.errors:
            return self._check(
                "configuration",
                False,
                "Database settings",
                "; ".join(status.errors),
                warning=True,
            )
        return self._check(
            "configuration",
            status.ready,
            "Core configuration",
            "synchronized" if status.ready else "; ".join(status.errors),
        )

    def _routing(self):
        checks = []
        with self.database.connect() as connection:
            destinations = connection.execute(
                """
                SELECT id, name, output_type, enabled, secret_id
                FROM destinations ORDER BY name_normalized
                """
            ).fetchall()
            broken_routes = connection.execute(
                """
                SELECT routes.name FROM routes
                LEFT JOIN destinations ON destinations.id = routes.destination_id
                WHERE routes.enabled = 1
                  AND (destinations.id IS NULL OR destinations.enabled = 0)
                ORDER BY routes.name_normalized
                """
            ).fetchall()
        missing = [
            str(row["name"])
            for row in destinations
            if bool(row["enabled"])
            and str(row["output_type"]) in {"discord", "teams", "slack", "webhook"}
            and row["secret_id"] is None
        ]
        checks.append(
            self._check(
                "destination_credentials",
                not missing,
                "Destination credentials",
                "available" if not missing else f"missing: {', '.join(missing[:5])}",
            )
        )
        names = [str(row["name"]) for row in broken_routes]
        checks.append(
            self._check(
                "routes",
                not names,
                "Enabled routes",
                "healthy" if not names else f"unavailable destination: {', '.join(names[:5])}",
            )
        )
        return checks

    def _backup_target(self):
        if self.configuration_sync is None:
            return self._check("external_backup", True, "External backup", "not configured")
        settings = self.configuration_sync.backup_settings()
        if not settings["external_enabled"]:
            return self._check("external_backup", True, "External backup", "disabled")
        path = Path(settings["external_path"])
        healthy = path.is_dir() and not path.is_symlink()
        return self._check(
            "external_backup",
            healthy,
            f"{settings['external_type'].upper()} backup target",
            "mounted" if healthy else "mounted path is unavailable",
        )

    def _deliveries(self):
        since = int(self.clock()) - 3600
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) FROM delivery_attempts
                WHERE created_at >= ? AND outcome = 'failed'
                """,
                (since,),
            ).fetchone()
        failures = int(row[0])
        return self._check(
            "recent_delivery",
            failures == 0,
            "Recent delivery failures",
            "none in the last hour" if failures == 0 else f"{failures} failed attempt(s) in the last hour",
            warning=True,
        )

    @staticmethod
    def _check(key, healthy, name, detail, warning=False):
        return {
            "key": key,
            "name": name,
            "status": "healthy" if healthy else "warning" if warning else "error",
            "detail": str(detail)[:500],
        }
