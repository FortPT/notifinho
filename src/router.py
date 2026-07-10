"""
Notifinho

router.py

Routes parsed notifications to one or more configured
outputs.
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

            output_name = destination.get("output")

            target = destination.get(
                "target",
                "default",
            )

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
