"""Private/shared destination metadata with strict secret separation."""

from __future__ import annotations

import json
import re
import sqlite3
import time
import uuid

from dataclasses import dataclass
from typing import Callable

from outputs.settings import OUTPUT_TYPES, normalize_output_settings
from storage.audit_events import AuditEventStore
from storage.database import Database
from storage.ownership import Actor, OwnershipPolicy
from storage.validation import normalized_identifier, normalized_name


_SECRET_KEY = re.compile(
    r"(?i)(authorization|cookie|password|secret|token|webhook|api[_-]?key)"
)
@dataclass(frozen=True)
class Destination:
    id: str
    owner_user_id: str
    name: str
    output_type: str
    settings: dict
    shared: bool
    enabled: bool
    secret_configured: bool
    created_at: int
    updated_at: int


@dataclass(frozen=True)
class DeliveryDestination:
    destination: Destination
    secret_id: str | None


class DestinationStore:
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
        output_type: str,
        *,
        secret_id: str | None = None,
        settings: dict | None = None,
        shared: bool = False,
        enabled: bool = True,
    ) -> Destination:
        OwnershipPolicy.require_write(actor, str(owner_user_id))
        if shared and not actor.is_admin:
            raise PermissionError("only administrators can create shared destinations")
        display, normalized = normalized_name(name, "destination name")
        _output_display, normalized_output = normalized_identifier(
            output_type,
            "output type",
            maximum=32,
        )
        if normalized_output not in OUTPUT_TYPES:
            raise ValueError("unsupported destination output type")
        raw_settings = {} if settings is None else settings
        if (
            isinstance(raw_settings, dict)
            and raw_settings.get("allow_private_network")
            and not actor.is_admin
        ):
            raise PermissionError(
                "only administrators can allow private-network destinations"
            )
        encoded_settings = self._settings(normalized_output, raw_settings)
        destination_id = uuid.uuid4().hex
        now = int(self.clock())
        try:
            with self.database.transaction() as connection:
                owner = connection.execute(
                    "SELECT enabled FROM users WHERE id = ?",
                    (str(owner_user_id),),
                ).fetchone()
                if owner is None:
                    raise KeyError("destination owner not found")
                if not bool(owner["enabled"]):
                    raise PermissionError("disabled users cannot own new destinations")
                if secret_id is not None:
                    secret = connection.execute(
                        "SELECT owner_user_id FROM secret_records WHERE id = ?",
                        (str(secret_id),),
                    ).fetchone()
                    if secret is None:
                        raise KeyError("destination secret not found")
                    if str(secret["owner_user_id"]) != str(owner_user_id):
                        raise PermissionError(
                            "destination and secret must have the same owner"
                        )
                connection.execute(
                    """
                    INSERT INTO destinations(
                        id, owner_user_id, name, name_normalized, output_type,
                        secret_id, settings_json, shared, enabled,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        destination_id,
                        str(owner_user_id),
                        display,
                        normalized,
                        normalized_output,
                        str(secret_id) if secret_id else None,
                        encoded_settings,
                        1 if shared else 0,
                        1 if enabled else 0,
                        now,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise ValueError(
                "destination name is already configured for this owner"
            ) from error
        destination = self.get(actor, destination_id)
        self._audit(
            actor,
            "destination.create",
            destination_id,
            "success",
            {"output_type": destination.output_type, "shared": destination.shared},
        )
        return destination

    def get(self, actor: Actor, destination_id: str) -> Destination:
        row = self._record(destination_id)
        OwnershipPolicy.require_read(
            actor,
            str(row["owner_user_id"]),
            bool(row["shared"]),
        )
        return self._destination(row)

    def list_visible(self, actor: Actor) -> list[Destination]:
        with self.database.connect() as connection:
            if actor.is_admin:
                rows = connection.execute(
                    "SELECT * FROM destinations ORDER BY name_normalized"
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM destinations
                    WHERE owner_user_id = ? OR shared = 1
                    ORDER BY name_normalized
                    """,
                    (actor.user_id,),
                ).fetchall()
        return [self._destination(row) for row in rows]

    def for_delivery(self, actor: Actor, destination_id: str) -> DeliveryDestination:
        target = self.for_delivery_metadata(actor, destination_id)
        if not target.destination.enabled:
            raise PermissionError("destination is disabled")
        return target

    def for_delivery_metadata(
        self,
        actor: Actor,
        destination_id: str,
    ) -> DeliveryDestination:
        """Return secret identity without resolving or exposing its value."""

        row = self._record(destination_id)
        OwnershipPolicy.require_read(
            actor,
            str(row["owner_user_id"]),
            bool(row["shared"]),
        )
        return DeliveryDestination(
            self._destination(row),
            str(row["secret_id"]) if row["secret_id"] is not None else None,
        )

    def set_enabled(
        self,
        actor: Actor,
        destination_id: str,
        enabled: bool,
    ) -> Destination:
        row = self._record(destination_id)
        OwnershipPolicy.require_write(actor, str(row["owner_user_id"]))
        now = int(self.clock())
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE destinations SET enabled = ?, updated_at = ? WHERE id = ?",
                (1 if enabled else 0, now, str(destination_id)),
            )
        self._audit(
            actor,
            "destination.enable" if enabled else "destination.disable",
            destination_id,
            "success",
        )
        return self.get(actor, destination_id)

    def set_shared(
        self,
        actor: Actor,
        destination_id: str,
        shared: bool,
    ) -> Destination:
        if not actor.is_admin:
            raise PermissionError("only administrators can change destination sharing")
        row = self._record(destination_id)
        now = int(self.clock())
        with self.database.transaction() as connection:
            if not shared:
                external_routes = int(
                    connection.execute(
                        """
                        SELECT COUNT(*) FROM routes
                        WHERE destination_id = ? AND owner_user_id != ?
                        """,
                        (str(destination_id), str(row["owner_user_id"])),
                    ).fetchone()[0]
                )
                if external_routes:
                    raise ValueError(
                        "shared destination is referenced by another user's route"
                    )
            connection.execute(
                "UPDATE destinations SET shared = ?, updated_at = ? WHERE id = ?",
                (1 if shared else 0, now, str(destination_id)),
            )
        self._audit(
            actor,
            "destination.share",
            destination_id,
            "success",
            {"shared": shared},
        )
        return self.get(actor, destination_id)

    def update_settings(
        self,
        actor: Actor,
        destination_id: str,
        settings: dict,
    ) -> Destination:
        row = self._record(destination_id)
        OwnershipPolicy.require_write(actor, str(row["owner_user_id"]))
        if (
            isinstance(settings, dict)
            and settings.get("allow_private_network")
            and not actor.is_admin
        ):
            raise PermissionError(
                "only administrators can allow private-network destinations"
            )
        encoded = self._settings(str(row["output_type"]), settings)
        now = int(self.clock())
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE destinations SET settings_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (encoded, now, str(destination_id)),
            )
        self._audit(actor, "destination.update", destination_id, "success")
        return self.get(actor, destination_id)

    def set_secret(
        self,
        actor: Actor,
        destination_id: str,
        secret_id: str,
    ) -> Destination:
        row = self._record(destination_id)
        OwnershipPolicy.require_write(actor, str(row["owner_user_id"]))
        with self.database.transaction() as connection:
            secret = connection.execute(
                "SELECT owner_user_id FROM secret_records WHERE id = ?",
                (str(secret_id),),
            ).fetchone()
            if secret is None:
                raise KeyError("destination secret not found")
            if str(secret["owner_user_id"]) != str(row["owner_user_id"]):
                raise PermissionError("destination and secret must have the same owner")
            connection.execute(
                "UPDATE destinations SET secret_id = ?, updated_at = ? WHERE id = ?",
                (str(secret_id), int(self.clock()), str(destination_id)),
            )
        self._audit(
            actor,
            "destination.secret",
            destination_id,
            "success",
            {"configured": True},
        )
        return self.get(actor, destination_id)

    def delete(self, actor: Actor, destination_id: str) -> None:
        row = self._record(destination_id)
        OwnershipPolicy.require_write(actor, str(row["owner_user_id"]))
        try:
            with self.database.transaction() as connection:
                connection.execute(
                    "DELETE FROM destinations WHERE id = ?",
                    (str(destination_id),),
                )
        except sqlite3.IntegrityError as error:
            raise ValueError("destination is referenced by a route") from error
        self._audit(actor, "destination.delete", destination_id, "success")

    def _record(self, destination_id: str):
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM destinations WHERE id = ?",
                (str(destination_id),),
            ).fetchone()
        if row is None:
            raise KeyError("destination not found")
        return row

    @staticmethod
    def _destination(row) -> Destination:
        return Destination(
            id=str(row["id"]),
            owner_user_id=str(row["owner_user_id"]),
            name=str(row["name"]),
            output_type=str(row["output_type"]),
            settings=json.loads(str(row["settings_json"])),
            shared=bool(row["shared"]),
            enabled=bool(row["enabled"]),
            secret_configured=row["secret_id"] is not None,
            created_at=int(row["created_at"]),
            updated_at=int(row["updated_at"]),
        )

    @classmethod
    def _settings(cls, output_type: str, settings: dict) -> str:
        if not isinstance(settings, dict):
            raise ValueError("destination settings must be an object")
        cls._reject_secrets(settings)
        normalized = normalize_output_settings(output_type, settings)
        try:
            encoded = json.dumps(
                normalized,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError) as error:
            raise ValueError("destination settings must contain JSON values") from error
        if len(encoded.encode("utf-8")) > 16 * 1024:
            raise ValueError("destination settings must not exceed 16384 bytes")
        return encoded

    @classmethod
    def _reject_secrets(cls, value, path="settings") -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if _SECRET_KEY.search(str(key)):
                    raise ValueError(f"{path}.{key} must use an owner-scoped secret")
                cls._reject_secrets(item, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                cls._reject_secrets(item, f"{path}.{index}")

    def _audit(self, actor, action, resource_id, outcome, details=None):
        if self.audit is not None:
            self.audit.write(
                actor,
                action,
                "destination",
                resource_id,
                outcome,
                details,
            )
