"""
Notifinho

router.py

Routes parsed notifications to one or more configured
outputs, with optional per-destination filters.
"""

from __future__ import annotations

from config import config
from logger import log
from models import Notification

from outputs.discord import DiscordOutput
from outputs.teams import TeamsOutput


class Router:

    def __init__(self):

        self.outputs = {
            "discord": DiscordOutput(),
            "teams": TeamsOutput(),
        }

        log.info(
            "Router initialized (%s output%s)",
            len(self.outputs),
            "" if len(self.outputs) == 1 else "s",
        )

    def route(
        self,
        notification: Notification,
    ) -> bool:

        route = config.get(
            "routing",
            notification.source,
        )

        if route is None:

            log.warning(
                "No routing configured for '%s'",
                notification.source,
            )

            return False

        routes = route.get("outputs")

        if routes is None:

            # Backwards compatibility with the original
            # single-output routing format.
            routes = [route]

        if not isinstance(routes, list):

            log.error(
                "Invalid routing configured for '%s'",
                notification.source,
            )

            return False

        success = False

        for destination in routes:

            if not isinstance(destination, dict):

                log.error(
                    "Invalid output routing configured for '%s'",
                    notification.source,
                )

                continue

            output_name = destination.get(
                "output",
            )

            target = destination.get(
                "target",
                "default",
            )

            if not self._destination_matches(
                notification,
                destination,
            ):

                log.info(
                    "Route filter skipped '%s' -> %s (%s)",
                    notification.source,
                    output_name,
                    target,
                )

                continue

            log.info(
                "Routing '%s' -> %s (%s)",
                notification.source,
                output_name,
                target,
            )

            output = self.outputs.get(
                output_name,
            )

            if output is None:

                log.error(
                    "Unknown output '%s'",
                    output_name,
                )

                continue

            try:

                sent = output.send(
                    notification,
                    target,
                )

            except Exception:

                log.exception(
                    "Failed to route '%s' -> %s (%s)",
                    notification.source,
                    output_name,
                    target,
                )

                continue

            if sent:

                success = True

            else:

                log.error(
                    "Failed to route '%s' -> %s (%s)",
                    notification.source,
                    output_name,
                    target,
                )

        return success

    def _destination_matches(
        self,
        notification: Notification,
        destination: dict,
    ) -> bool:
        """
        Check optional filters configured for an output route.

        Routes without a match block remain unconditional.

        Currently supported:

        match:
          hosts:
            - "VM-07 | Palworld"
        """

        match = destination.get(
            "match",
        )

        if match is None:

            return True

        if not isinstance(match, dict):

            log.error(
                "Invalid route match configuration for '%s'",
                notification.source,
            )

            return False

        hosts = match.get(
            "hosts",
        )

        if hosts is not None:

            if isinstance(hosts, str):

                hosts = [
                    hosts,
                ]

            if not isinstance(hosts, list):

                log.error(
                    "Route host filter for '%s' must be a list.",
                    notification.source,
                )

                return False

            metadata = notification.metadata or {}

            notification_host = str(
                metadata.get(
                    "host",
                    "",
                )
            ).strip()

            if not notification_host:

                log.warning(
                    "Route requires a host match, but notification "
                    "source '%s' has no host metadata.",
                    notification.source,
                )

                return False

            allowed_hosts = {
                str(host).strip().casefold()
                for host in hosts
                if str(host).strip()
            }

            if notification_host.casefold() not in allowed_hosts:

                log.info(
                    "Host '%s' did not match allowed route hosts: %s",
                    notification_host,
                    ", ".join(
                        str(host)
                        for host in hosts
                    ),
                )

                return False

        return True
