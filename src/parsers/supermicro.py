"""Supermicro BMC/IPMI email adapter."""

from parsers.redfish import HardwareEmailParser


class Parser(HardwareEmailParser):
    source = "supermicro"
    vendor_name = "Supermicro BMC"
    markers = ("supermicro", "super micro", "ipmi", "bmc")
