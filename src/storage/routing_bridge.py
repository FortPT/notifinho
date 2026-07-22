"""Route legacy SMTP and webhook notifications through platform-owned routes."""

from __future__ import annotations

from outputs.platform import PlatformOutputRegistry
from storage.delivery import (
    DeliveryHistoryStore,
    DeliverySummary,
    PlatformDeliveryService,
)
from storage.destinations import DestinationStore
from storage.ownership import Actor
from storage.routes import RouteStore
from storage.secrets import SecretStore


class PlatformRoutingBridge:
    """Deliver one infrastructure event to every enabled platform route owner."""

    def __init__(self, database, *, registry=None):
        self.database = database
        self.routes = RouteStore(database)
        self.destinations = DestinationStore(database)
        self.secrets = SecretStore(database)
        self.history = DeliveryHistoryStore(database)
        self.registry = registry or PlatformOutputRegistry()
        self.delivery = PlatformDeliveryService(
            self.routes,
            self.destinations,
            self.secrets,
            self.history,
            self.registry.delivery_adapters(),
        )

    def route(self, notification) -> DeliverySummary:
        matched = delivered = failed = attempts = 0
        for owner_id in self._owners(notification):
            summary = self.delivery.deliver(
                Actor(owner_id, "user"),
                notification,
            )
            matched += summary.matched_routes
            delivered += summary.delivered
            failed += summary.failed
            attempts += summary.attempts
        return DeliverySummary(matched, delivered, failed, attempts)

    def _owners(self, notification) -> tuple[str, ...]:
        source = str(notification.source or "").strip().casefold()
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT routes.owner_user_id
                FROM routes
                JOIN destinations ON destinations.id = routes.destination_id
                JOIN users ON users.id = routes.owner_user_id
                WHERE routes.enabled = 1
                  AND destinations.enabled = 1
                  AND users.enabled = 1
                  AND (routes.source = ? OR routes.source = '*')
                ORDER BY routes.owner_user_id
                """,
                (source,),
            ).fetchall()
        owners = []
        for row in rows:
            owner_id = str(row["owner_user_id"])
            actor = Actor(owner_id, "user")
            if self.routes.matching(actor, owner_id, notification):
                owners.append(owner_id)
        return tuple(owners)
