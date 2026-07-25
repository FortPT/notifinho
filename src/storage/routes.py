"""User-owned route CRUD and deterministic notification filter matching."""

from __future__ import annotations

import fnmatch
import json
import sqlite3
import time
import unicodedata
import uuid

from dataclasses import dataclass
from typing import Callable

from integrations.catalog import canonical_source
from models import Notification
from storage.audit_events import AuditEventStore
from storage.database import Database
from storage.ownership import Actor, OwnershipPolicy
from storage.validation import normalized_identifier, normalized_name


_FILTER_KEYS = {
    "hosts", "events", "severities", "statuses",
    "exclude_hosts", "exclude_events", "exclude_severities", "exclude_statuses",
}
ROUTE_PRIORITY_VALUES = {
    "critical": 10,
    "high": 25,
    "normal": 50,
    "low": 75,
    "lowest": 100,
}


def route_priority_value(value) -> int:
    if isinstance(value, str) and value.strip().casefold() in ROUTE_PRIORITY_VALUES:
        return ROUTE_PRIORITY_VALUES[value.strip().casefold()]
    number = int(value)
    if not 0 <= number <= 1000:
        raise ValueError("route priority must be between 0 and 1000")
    return number


def route_priority_name(value) -> str:
    number = route_priority_value(value)
    if number <= 10:
        return "critical"
    if number <= 25:
        return "high"
    if number <= 50:
        return "normal"
    if number <= 75:
        return "low"
    return "lowest"


@dataclass(frozen=True)
class Route:
    id: str
    owner_user_id: str
    destination_id: str
    name: str
    source: str
    filters: dict[str, tuple[str, ...]]
    priority: int
    enabled: bool
    created_at: int
    updated_at: int
    input_type: str = ""


class RouteStore:
    def __init__(
        self,
        database: Database,
        *,
        audit: AuditEventStore | None = None,
        clock: Callable[[], float] = time.time,
    ):
        self.database = database
        self.audit = audit
        self.clock = clock

    def create(
        self,
        actor: Actor,
        owner_user_id: str,
        name: str,
        source: str,
        destination_id: str,
        *,
        input_type: str = "",
        filters: dict | None = None,
        priority: int = 100,
        enabled: bool = True,
    ) -> Route:
        OwnershipPolicy.require_write(actor, str(owner_user_id))
        display, normalized = normalized_name(name, "route name")
        normalized_source = self._source(source)
        if normalized_source == "*" and not actor.is_admin:
            raise PermissionError("wildcard routes require an administrator")
        normalized_input = self._input_type(input_type)
        encoded_filters = self._filters(filters or {})
        bounded_priority = route_priority_value(priority)
        route_id = uuid.uuid4().hex
        now = int(self.clock())
        try:
            with self.database.transaction() as connection:
                owner = connection.execute(
                    "SELECT enabled FROM users WHERE id = ?",
                    (str(owner_user_id),),
                ).fetchone()
                if owner is None:
                    raise KeyError("route owner not found")
                if not bool(owner["enabled"]):
                    raise PermissionError("disabled users cannot own new routes")
                destination = connection.execute(
                    """
                    SELECT owner_user_id, shared FROM destinations WHERE id = ?
                    """,
                    (str(destination_id),),
                ).fetchone()
                if destination is None:
                    raise KeyError("route destination not found")
                if (
                    str(destination["owner_user_id"]) != str(owner_user_id)
                    and not bool(destination["shared"])
                ):
                    raise PermissionError(
                        "route destination must be owned by the user or shared"
                    )
                connection.execute(
                    """
                    INSERT INTO routes(
                        id, owner_user_id, destination_id, name,
                        name_normalized, source, input_type, filters_json,
                        priority, enabled, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        route_id,
                        str(owner_user_id),
                        str(destination_id),
                        display,
                        normalized,
                        normalized_source,
                        normalized_input,
                        encoded_filters,
                        bounded_priority,
                        1 if enabled else 0,
                        now,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise ValueError("route name is already configured for this owner") from error
        route = self.get(actor, route_id)
        self._audit(
            actor,
            "route.create",
            route_id,
            "success",
            {"source": route.source, "destination_id": route.destination_id},
        )
        return route

    def get(self, actor: Actor, route_id: str) -> Route:
        row = self._record(route_id)
        OwnershipPolicy.require_read(actor, str(row["owner_user_id"]))
        return self._route(row)

    def list_for_owner(self, actor: Actor, owner_user_id: str) -> list[Route]:
        OwnershipPolicy.require_read(actor, str(owner_user_id))
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM routes
                WHERE owner_user_id = ? ORDER BY priority, name_normalized
                """,
                (str(owner_user_id),),
            ).fetchall()
        return [self._route(row) for row in rows]

    def list_visible(self, actor: Actor) -> list[Route]:
        """List routes the actor may inspect without granting write access."""

        items, errors = self.list_visible_safe(actor)
        if errors:
            raise ValueError(errors[0]["message"])
        return items

    def list_visible_safe(self, actor: Actor) -> tuple[list[Route], list[dict]]:
        """Return every readable valid route plus per-row failures."""

        with self.database.connect() as connection:
            if actor.is_admin:
                rows = connection.execute(
                    """
                    SELECT routes.* FROM routes
                    ORDER BY routes.priority, routes.name_normalized
                    """
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT routes.* FROM routes
                    JOIN destinations
                      ON destinations.id = routes.destination_id
                    WHERE routes.owner_user_id = ? OR destinations.shared = 1
                    ORDER BY routes.priority, routes.name_normalized
                    """,
                    (actor.user_id,),
                ).fetchall()
        items = []
        errors = []
        for row in rows:
            try:
                items.append(self._route(row))
            except Exception as error:
                errors.append(
                    {
                        "resource_id": str(row["id"]),
                        "resource": str(row["name"]),
                        "code": "route_record_invalid",
                        "message": f"Route {str(row['name'])!r} could not be loaded: {error}",
                    }
                )
        return items, errors

    def matching(
        self,
        actor: Actor,
        owner_user_id: str,
        notification: Notification,
    ) -> list[Route]:
        OwnershipPolicy.require_read(actor, str(owner_user_id))
        source = canonical_source(notification.source)
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT routes.* FROM routes
                JOIN destinations ON destinations.id = routes.destination_id
                WHERE routes.owner_user_id = ?
                  AND routes.enabled = 1
                  AND destinations.enabled = 1
                  AND (routes.source = ? OR routes.source = '*')
                ORDER BY routes.priority, routes.name_normalized
                """,
                (str(owner_user_id), source),
            ).fetchall()
        routes = [self._route(row) for row in rows]
        matched = [route for route in routes if self.matches(route, notification)]

        # Wildcard routes are fallback-only. A dedicated integration route must
        # never duplicate the same event into a generic/default destination.
        specific = [route for route in matched if route.source != "*"]
        selected = specific if specific else [route for route in matched if route.source == "*"]

        # Multiple matching filters may intentionally target the same output,
        # but one event should produce at most one delivery per destination.
        unique = []
        seen_destinations = set()
        for route in selected:
            if route.destination_id in seen_destinations:
                continue
            seen_destinations.add(route.destination_id)
            unique.append(route)
        return unique

    def set_enabled(self, actor: Actor, route_id: str, enabled: bool) -> Route:
        row = self._record(route_id)
        OwnershipPolicy.require_write(actor, str(row["owner_user_id"]))
        now = int(self.clock())
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE routes SET enabled = ?, updated_at = ? WHERE id = ?",
                (1 if enabled else 0, now, str(route_id)),
            )
        self._audit(
            actor,
            "route.enable" if enabled else "route.disable",
            route_id,
            "success",
        )
        return self.get(actor, route_id)

    def update(
        self,
        actor: Actor,
        route_id: str,
        *,
        name=None,
        source=None,
        input_type=None,
        destination_id=None,
        filters=None,
        priority=None,
        enabled=None,
    ) -> Route:
        row = self._record(route_id)
        owner_user_id = str(row["owner_user_id"])
        OwnershipPolicy.require_write(actor, owner_user_id)

        display, normalized = normalized_name(
            row["name"] if name is None else name,
            "route name",
        )
        normalized_source = self._source(
            row["source"] if source is None else source,
        )
        if normalized_source == "*" and not actor.is_admin:
            raise PermissionError("wildcard routes require an administrator")
        normalized_input = self._input_type(
            row["input_type"] if input_type is None else input_type,
        )
        encoded_filters = self._filters(
            json.loads(str(row["filters_json"])) if filters is None else filters,
        )
        bounded_priority = route_priority_value(
            row["priority"] if priority is None else priority
        )
        if enabled is None:
            enabled_value = bool(row["enabled"])
        elif isinstance(enabled, bool):
            enabled_value = enabled
        else:
            raise ValueError("route enabled must be a boolean")
        next_destination = str(
            row["destination_id"] if destination_id is None else destination_id
        )
        now = int(self.clock())
        try:
            with self.database.transaction() as connection:
                destination = connection.execute(
                    "SELECT owner_user_id, shared FROM destinations WHERE id = ?",
                    (next_destination,),
                ).fetchone()
                if destination is None:
                    raise KeyError("route destination not found")
                if (
                    str(destination["owner_user_id"]) != owner_user_id
                    and not bool(destination["shared"])
                ):
                    raise PermissionError(
                        "route destination must be owned by the user or shared"
                    )
                connection.execute(
                    """
                    UPDATE routes
                    SET name = ?, name_normalized = ?, source = ?,
                        input_type = ?, destination_id = ?, filters_json = ?,
                        priority = ?, enabled = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        display,
                        normalized,
                        normalized_source,
                        normalized_input,
                        next_destination,
                        encoded_filters,
                        bounded_priority,
                        1 if enabled_value else 0,
                        now,
                        str(route_id),
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise ValueError(
                "route name is already configured for this owner"
            ) from error
        route = self.get(actor, route_id)
        self._audit(
            actor,
            "route.update",
            route_id,
            "success",
            {"source": route.source, "destination_id": route.destination_id},
        )
        return route

    def delete(self, actor: Actor, route_id: str) -> None:
        row = self._record(route_id)
        OwnershipPolicy.require_write(actor, str(row["owner_user_id"]))
        with self.database.transaction() as connection:
            connection.execute("DELETE FROM routes WHERE id = ?", (str(route_id),))
        self._audit(actor, "route.delete", route_id, "success")

    @classmethod
    def matches(cls, route: Route, notification: Notification) -> bool:
        source = canonical_source(notification.source)
        route_source = route.source if route.source == "*" else canonical_source(route.source)
        if route_source not in {"*", source}:
            return False
        if route.input_type:
            observed_input = cls._normalized(
                (notification.metadata or {}).get("_input_type")
            )
            if observed_input != route.input_type:
                return False
        filters = route.filters
        if "hosts" in filters:
            hosts = cls._candidates(
                notification,
                "host",
                "hostname",
                "device",
                "node",
            )
            if not hosts or not cls._any_pattern(hosts, filters["hosts"]):
                return False
        if "events" in filters:
            events = cls._candidates(
                notification,
                "event",
                "event_type",
                "event_name",
            )
            events.extend(
                cls._normalized(item)
                for item in (notification.category, notification.title)
                if str(item or "").strip()
            )
            if not events or not cls._any_pattern(events, filters["events"]):
                return False
        if "severities" in filters:
            severities = cls._candidates(notification, "severity")
            if notification.status:
                severities.append(cls._normalized(notification.status))
            if not severities or not cls._any_pattern(
                severities,
                filters["severities"],
            ):
                return False
        statuses = [cls._normalized(notification.status)] if notification.status else []
        statuses.extend(cls._candidates(notification, "state", "status"))
        if "statuses" in filters:
            if not statuses or not cls._any_pattern(statuses, filters["statuses"]):
                return False

        excluded = {
            "exclude_hosts": cls._candidates(
                notification, "host", "hostname", "device", "node"
            ),
            "exclude_events": cls._candidates(
                notification, "event", "event_type", "event_name"
            ),
            "exclude_severities": cls._candidates(notification, "severity"),
            "exclude_statuses": statuses,
        }
        excluded["exclude_events"].extend(
            cls._normalized(item)
            for item in (notification.category, notification.title)
            if str(item or "").strip()
        )
        if notification.status:
            excluded["exclude_severities"].append(
                cls._normalized(notification.status)
            )
        for key, values in excluded.items():
            if key in filters and values and cls._any_pattern(values, filters[key]):
                return False
        return True

    def _record(self, route_id: str):
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM routes WHERE id = ?",
                (str(route_id),),
            ).fetchone()
        if row is None:
            raise KeyError("route not found")
        return row

    @staticmethod
    def _route(row) -> Route:
        decoded = json.loads(str(row["filters_json"]))
        return Route(
            id=str(row["id"]),
            owner_user_id=str(row["owner_user_id"]),
            destination_id=str(row["destination_id"]),
            name=str(row["name"]),
            source=str(row["source"]),
            filters={key: tuple(values) for key, values in decoded.items()},
            priority=int(row["priority"]),
            enabled=bool(row["enabled"]),
            created_at=int(row["created_at"]),
            updated_at=int(row["updated_at"]),
            input_type=str(row["input_type"] or "") if "input_type" in row.keys() else "",
        )

    @classmethod
    def _filters(cls, filters: dict) -> str:
        if not isinstance(filters, dict):
            raise ValueError("route filters must be an object")
        unknown = set(filters) - _FILTER_KEYS
        if unknown:
            raise ValueError(f"unsupported route filter: {sorted(unknown)[0]}")
        normalized = {}
        for key, values in filters.items():
            if isinstance(values, str):
                values = [values]
            if not isinstance(values, (list, tuple)) or not values:
                raise ValueError(f"route filter {key} must be a non-empty list")
            items = []
            for value in values:
                item = cls._normalized(value)
                if not item or len(item) > 128:
                    raise ValueError(
                        f"route filter {key} values must contain 1 to 128 characters"
                    )
                if item not in items:
                    items.append(item)
            if len(items) > 64:
                raise ValueError(f"route filter {key} must not exceed 64 values")
            normalized[key] = items
        encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > 16 * 1024:
            raise ValueError("route filters must not exceed 16384 bytes")
        return encoded

    @staticmethod
    def _input_type(value) -> str:
        normalized = str(value or "").strip().casefold()
        if normalized not in {"", "smtp", "http", "redfish"}:
            raise ValueError("route input type must be smtp, http, or redfish")
        return normalized

    @staticmethod
    def _source(value: str) -> str:
        if str(value or "").strip() == "*":
            return "*"
        _display, normalized = normalized_identifier(
            value,
            "route source",
            maximum=64,
        )
        return normalized

    @classmethod
    def _candidates(cls, notification: Notification, *keys: str) -> list[str]:
        metadata = notification.metadata or {}
        values = []
        for key in keys:
            value = metadata.get(key)
            if value not in (None, ""):
                values.append(cls._normalized(value))
        return values

    @staticmethod
    def _any_pattern(values, patterns) -> bool:
        return any(
            fnmatch.fnmatchcase(value, pattern)
            for value in values
            for pattern in patterns
        )

    @staticmethod
    def _normalized(value) -> str:
        return unicodedata.normalize("NFKC", str(value or "")).strip().casefold()

    def _audit(self, actor, action, resource_id, outcome, details=None):
        if self.audit is not None:
            self.audit.write(actor, action, "route", resource_id, outcome, details)
