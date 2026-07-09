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


class Router:

    def __init__(self):

        #
        # Output registry
        #

        self.outputs = {
            "discord": DiscordOutput(),
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

        #
        # Lookup routing
        #

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

        output_name = route.get("output")

        target = route.get("target")

        log.info(
            "Routing '%s' -> %s (%s)",
            notification.source,
            output_name,
            target,
        )

        #
        # Get output implementation
        #

        output = self.outputs.get(
            output_name,
        )

        if output is None:

            log.error(
                "Unknown output '%s'",
                output_name,
            )

            return False

        #
        # Send notification
        #

        return output.send(
            notification,
            target,
        )
