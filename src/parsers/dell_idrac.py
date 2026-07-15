"""Dell iDRAC email-alert adapter."""

from parsers.redfish import HardwareEmailParser


class Parser(HardwareEmailParser):
    source = "dell_idrac"
    vendor_name = "Dell iDRAC"
    markers = ("dell idrac", "idrac", "lifecycle controller", "dell emc")
