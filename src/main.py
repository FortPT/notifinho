"""
Notifinho

main.py

Application entry point.

Starts the application and initializes all
core components.
"""

from __future__ import annotations

import signal
import sys
import time
from threading import Event

from dispatcher import Dispatcher
from inputs.http import HTTPInput
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

    smtp = None
    http = None
    shutdown_requested = Event()

    def request_shutdown(signum, _frame):
        signal_name = signal.Signals(signum).name
        log.info("Shutdown requested by %s.", signal_name)
        shutdown_requested.set()

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)

    try:

        dispatcher = Dispatcher()

        router = Router()

        smtp = SMTPInput(
            dispatcher=dispatcher,
            router=router,
        )

        smtp.start()

        http = HTTPInput(
            dispatcher=dispatcher,
            router=router,
        )

        http.start()

        #
        # Keep the application alive
        #

        while not shutdown_requested.is_set():

            time.sleep(1)

    except KeyboardInterrupt:

        log.info("Shutdown requested by user.")

    except Exception:

        log.exception("Unhandled exception.")

        return 1

    finally:

        if http is not None:

            http.stop()

        if smtp is not None:

            smtp.stop()

    log.info("%s stopped.", APP_NAME)

    return 0


if __name__ == "__main__":

    sys.exit(main())
