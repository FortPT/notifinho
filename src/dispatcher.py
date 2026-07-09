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
from parsers.xo import Parser as XOParser
from parsers.zabbix import Parser as ZabbixParser
from parsers.truenas import Parser as TrueNASParser
from parsers.proxmox import Parser as ProxmoxParser


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

        subject = message.get("Subject", "")

        sender = message.get("From", "")

        log.info("Subject : %s", subject)

        log.info("Sender  : %s", sender)

        #
        # Xen Orchestra
        #

        if "Xen Orchestra" in sender:

            log.info("Detected Xen Orchestra email")

            return self.xo_parser.parse(message)

        #
        # Zabbix
        #

        if "Zabbix" in sender:

            log.info("Detected Zabbix email")

            return self.zabbix_parser.parse(message)

        #
        # TrueNAS
        #

        if "TrueNAS" in sender:

            log.info("Detected TrueNAS email")

            return self.truenas_parser.parse(message)

        #
        # Proxmox
        #

        if "Proxmox" in sender:

            log.info("Detected Proxmox email")

            return self.proxmox_parser.parse(message)

        #
        # Generic
        #

        log.info("Using generic parser")

        return self.generic_parser.parse(message)
