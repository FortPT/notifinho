"""
Notifinho

main.py

Application entry point.

Starts the application and initializes all
core components.
"""

from __future__ import annotations

import sys
import time

from dispatcher import Dispatcher
from inputs.smtp import SMTPInput
from logger import log
from router import Router
from version import APP_NAME, VERSION


def main() -> int:
    """
    Application entry point.
    """

    log.info("")
    log.info("========================================")
    log.info("%s %s", APP_NAME, VERSION)
    log.info("========================================")
    log.info("Starting application...")
    log.info("")

    try:

        dispatcher = Dispatcher()

        router = Router()

        smtp = SMTPInput(
            dispatcher=dispatcher,
            router=router,
        )

        smtp.start()

        #
        # Keep the application alive
        #

        while True:

            time.sleep(60)

    except KeyboardInterrupt:

        log.info("Shutdown requested by user.")

    except Exception:

        log.exception("Unhandled exception.")

        return 1

    log.info("%s stopped.", APP_NAME)

    return 0


if __name__ == "__main__":

    sys.exit(main())
