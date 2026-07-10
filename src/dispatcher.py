"""
Notifinho

dispatcher.py

Receives email messages and dispatches them to the
appropriate parser based on their source.
"""

from __future__ import annotations

from email.message import EmailMessage

from logger import log

from parsers.generic import Parser as GenericParser
from parsers.proxmox import Parser as ProxmoxParser
from parsers.truenas import Parser as TrueNASParser
from parsers.xo import Parser as XOParser
from parsers.zabbix import Parser as ZabbixParser


class Dispatcher:

    def __init__(self):

        self.generic_parser = GenericParser()

        self.xo_parser = XOParser()

        self.zabbix_parser = ZabbixParser()

        self.truenas_parser = TrueNASParser()

        self.proxmox_parser = ProxmoxParser()

        log.info("Dispatcher initialized")

    def parse(
        self,
        message: EmailMessage,
    ):

        subject = str(
            message.get(
                "Subject",
                "",
            )
        )

        sender = str(
            message.get(
                "From",
                "",
            )
        )

        sender_lower = sender.lower()

        log.info(
            "Subject : %s",
            subject,
        )

        log.info(
            "Sender  : %s",
            sender,
        )

        #
        # Xen Orchestra
        #

        if "xen orchestra" in sender_lower:

            log.info(
                "Detected Xen Orchestra email"
            )

            return self.xo_parser.parse(
                message,
            )

        #
        # Zabbix
        #

        if "zabbix" in sender_lower:

            log.info(
                "Detected Zabbix email"
            )

            return self.zabbix_parser.parse(
                message,
            )

        #
        # TrueNAS
        #

        if "truenas" in sender_lower:

            log.info(
                "Detected TrueNAS email"
            )

            return self.truenas_parser.parse(
                message,
            )

        #
        # Proxmox
        #

        if "proxmox" in sender_lower:

            log.info(
                "Detected Proxmox email"
            )

            return self.proxmox_parser.parse(
                message,
            )

        #
        # Generic
        #

        log.info(
            "Using generic parser"
        )

        return self.generic_parser.parse(
            message,
        )
