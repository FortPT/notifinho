"""
Notifinho

smtp.py

SMTP input server.
"""

from __future__ import annotations

from datetime import datetime
from email import message_from_bytes
from email.policy import default
from pathlib import Path

from aiosmtpd.controller import Controller

from config import config
from logger import log


class Handler:

    def __init__(
        self,
        dispatcher,
        router,
    ):

        self.dispatcher = dispatcher
        self.router = router

    async def handle_DATA(
        self,
        server,
        session,
        envelope,
    ):

        log.info(
            "Email received from %s",
            envelope.mail_from,
        )

        log.info(
            "Recipients: %s",
            ", ".join(envelope.rcpt_tos),
        )

        #
        # Save raw email
        #

        email_dir = Path(
            "/notifinho/logs/emails"
        )

        email_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        filename = (
            datetime.now().strftime(
                "%Y%m%d-%H%M%S-%f"
            )
            + ".eml"
        )

        filepath = email_dir / filename

        filepath.write_bytes(
            envelope.original_content
        )

        log.info(
            "Saved raw email: %s",
            filepath,
        )

        #
        # Parse email
        #

        message = message_from_bytes(
            envelope.original_content,
            policy=default,
        )

        notification = self.dispatcher.parse(
            message,
        )

        if notification is not None:

            self.router.route(
                notification,
            )

            log.info(
                "Notification created from '%s'",
                notification.source,
            )

        log.info(
            "SMTP transaction completed."
        )

        return "250 Message accepted"


class SMTPInput:

    def __init__(
        self,
        dispatcher,
        router,
    ):

        host = config.get(
            "smtp",
            "host",
            default="0.0.0.0",
        )

        port = config.get(
            "smtp",
            "port",
            default=8025,
        )

        self.controller = Controller(
            Handler(
                dispatcher,
                router,
            ),
            hostname=host,
            port=port,
        )

    def start(self):

        log.info(
            "Starting SMTP server..."
        )

        self.controller.start()

        log.info(
            "Listening on %s:%s",
            self.controller.hostname,
            self.controller.port,
        )
