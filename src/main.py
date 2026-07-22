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
from datetime import datetime, timezone
from threading import Event

from config import config
from dispatcher import Dispatcher
from inputs.http import HTTPInput
from inputs.smtp import SMTPInput
from logger import log
from router import Router
from storage.runtime import initialize_state
from storage.bootstrap import BootstrapStore
from storage.backup_scheduler import BackupScheduler
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
    backup_scheduler = None
    shutdown_requested = Event()

    def request_shutdown(signum, _frame):
        signal_name = signal.Signals(signum).name
        log.info("Shutdown requested by %s.", signal_name)
        shutdown_requested.set()

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)

    try:

        state_database = initialize_state(config)

        if state_database is not None:

            log.info(
                "Platform state initialized (schema %s).",
                state_database.schema_version,
            )

            bootstrap = BootstrapStore(state_database).rotate_for_startup()
            if bootstrap is not None:
                expires = datetime.fromtimestamp(
                    bootstrap.expires_at,
                    tz=timezone.utc,
                ).isoformat()
                print("", flush=True)
                print("SECURE FIRST-RUN SETUP REQUIRED", flush=True)
                print(
                    "Open the Notifinho WebUI over HTTPS and enter this "
                    "single-use setup token:",
                    flush=True,
                )
                print(bootstrap.token, flush=True)
                print(f"Token expires at {expires}.", flush=True)
                print(
                    "It rotates when Notifinho restarts until an administrator exists.",
                    flush=True,
                )
                print("", flush=True)

            backup_scheduler = BackupScheduler(state_database, config)
            backup_scheduler.start()

        dispatcher = Dispatcher()

        router = Router(state_database) if state_database is not None else Router()

        smtp = SMTPInput(
            dispatcher=dispatcher,
            router=router,
        )

        smtp.start()

        http_arguments = {
            "dispatcher": dispatcher,
            "router": router,
        }
        if state_database is not None:
            http_arguments["platform_database"] = state_database
        http = HTTPInput(**http_arguments)

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

        if backup_scheduler is not None:

            backup_scheduler.stop()

        if http is not None:

            http.stop()

        if smtp is not None:

            smtp.stop()

    log.info("%s stopped.", APP_NAME)

    return 0


if __name__ == "__main__":

    sys.exit(main())
