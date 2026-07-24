"""Persistent category overrides for built-in integrations."""

from __future__ import annotations

import time

from integrations.catalog import CATEGORIES, canonical_source, integration


class IntegrationCategoryStore:
    def __init__(self, database):
        self.database = database

    def list_overrides(self) -> dict[str, str]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT integration_source, category
                FROM integration_categories
                ORDER BY integration_source
                """
            ).fetchall()
        return {
            str(row["integration_source"]): str(row["category"])
            for row in rows
        }

    def set_category(self, source: str, category: str) -> None:
        source = canonical_source(source)
        category = str(category or "").strip().casefold()
        category = {
            "servers": "hardware",
            "services": "monitoring",
            "applications": "generic",
            "controllers": "networking",
        }.get(category, category)
        if integration(source) is None:
            raise KeyError("integration not found")
        if category not in CATEGORIES:
            raise ValueError("integration category is invalid")
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO integration_categories(
                    integration_source, category, updated_at
                ) VALUES (?, ?, ?)
                ON CONFLICT(integration_source) DO UPDATE SET
                    category = excluded.category,
                    updated_at = excluded.updated_at
                """,
                (source, category, int(time.time())),
            )

    def import_legacy(self, values) -> int:
        if not isinstance(values, dict):
            return 0
        count = 0
        for source, category in values.items():
            try:
                self.set_category(source, category)
            except (KeyError, ValueError):
                continue
            count += 1
        return count
