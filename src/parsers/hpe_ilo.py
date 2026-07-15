"""HPE iLO AlertMail adapter."""

from parsers.redfish import HardwareEmailParser


class Parser(HardwareEmailParser):
    source = "hpe_ilo"
    vendor_name = "HPE iLO"
    markers = ("hpe ilo", "hp ilo", "hewlett packard enterprise", "alertmail")
