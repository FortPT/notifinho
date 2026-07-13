"""Parser for UniFi Network Alarm Manager webhook envelopes."""

from __future__ import annotations

from datetime import datetime, timezone

from models import Notification


def normalize_vendor_severity(
    value,
    event_name: str = "",
    message: str = "",
) -> tuple[str, str]:
    """Provisional mapping kept in one place until more samples are known.

    UniFi's numeric scale is preserved separately in metadata. A routine client
    disconnect at the discovered severity ``2`` remains informational unless
    stronger failure wording is present.
    """

    try:
        numeric = int(value)
    except (TypeError, ValueError):
        numeric = None

    text = f"{event_name} {message}".casefold()
    critical_markers = (
        "critical",
        "failed",
        "failure",
        "offline",
        "unreachable",
        "security threat",
    )
    warning_markers = (
        "warning",
        "degraded",
        "high interference",
        "packet loss",
    )

    if any(marker in text for marker in critical_markers) or (
        numeric is not None and numeric >= 4
    ):
        return "failure", "critical"
    if any(marker in text for marker in warning_markers) or numeric == 3:
        return "warning", "warning"
    return "information", "information"


class Parser:
    """Validate and normalize one Network webhook."""

    @staticmethod
    def is_envelope(payload) -> bool:
        if not isinstance(payload, dict):
            return False
        parameters = payload.get("parameters")
        if payload.get("app") != "network" or not isinstance(parameters, dict):
            return False
        required = {"alarm_id", "name", "message", "severity"}
        if not required.issubset(payload):
            return False
        has_unifi_parameter = any(
            isinstance(key, str) and key.startswith("UNIFI")
            for key in parameters
        )
        return bool(
            has_unifi_parameter
            or payload.get("deviceEventClassId")
            or payload.get("version")
        )

    def parse(self, payload: dict) -> Notification:
        if not self.is_envelope(payload):
            raise ValueError("invalid UniFi Network webhook envelope")

        parameters = payload.get("parameters") or {}
        event_name = self._text(payload.get("name")) or "UniFi Network event"
        message = self._text(payload.get("message"))
        status, severity = normalize_vendor_severity(
            payload.get("severity"),
            event_name,
            message,
        )
        event_time = self._event_time(parameters.get("UNIFIutcTime"))
        client_alias = self._text(parameters.get("UNIFIclientAlias"))
        client_hostname = self._text(parameters.get("UNIFIclientHostname"))

        notification = Notification(
            source="unifi_network",
            category=self._text(parameters.get("UNIFIcategory")) or "network",
            status=status,
            title=event_name,
            subject=event_name,
            body=message or event_name,
            start_time=event_time,
            duration=self._text(parameters.get("UNIFIduration")),
        )
        notification.metadata = {
            "provider": "UniFi Network",
            "event_name": event_name,
            "category": notification.category,
            "severity": severity,
            "vendor_severity": payload.get("severity"),
            "message": message,
            "controller": self._text(parameters.get("UNIFIhost")),
            "host": self._text(parameters.get("UNIFIhost")),
            "client_alias": client_alias,
            "client_hostname": client_hostname,
            "client_display_name": client_alias or client_hostname,
            "client_ip": self._text(parameters.get("UNIFIclientIp")),
            "client_mac": self._text(parameters.get("UNIFIclientMac")),
            "network_name": self._text(parameters.get("UNIFInetworkName")),
            "network_subnet": self._text(parameters.get("UNIFInetworkSubnet")),
            "network_vlan": self._text(parameters.get("UNIFInetworkVlan")),
            "wifi_name": self._text(parameters.get("UNIFIwifiName")),
            "wifi_band": self._text(parameters.get("UNIFIwifiBand")),
            "wifi_channel": self._text(parameters.get("UNIFIwifiChannel")),
            "wifi_rssi": self._text(parameters.get("UNIFIlastConnectedToWiFiRssi")),
            "last_device_name": self._text(
                parameters.get("UNIFIlastConnectedToDeviceName")
            ),
            "last_device_model": self._text(
                parameters.get("UNIFIlastConnectedToDeviceModel")
            ),
            "last_device_ip": self._text(
                parameters.get("UNIFIlastConnectedToDeviceIp")
            ),
            "last_device_mac": self._text(
                parameters.get("UNIFIlastConnectedToDeviceMac")
            ),
            "duration": notification.duration,
            "event_time": event_time,
            "alarm_id": self._text(payload.get("alarm_id")),
            "device_event_class_id": self._text(
                payload.get("deviceEventClassId")
            ),
            "parser_confidence": "high",
        }
        return notification

    def _event_time(self, value) -> str:
        text = self._text(value)
        if not text:
            return ""
        try:
            numeric = float(text)
            if numeric > 10_000_000_000:
                numeric /= 1000
            return datetime.fromtimestamp(numeric, tz=timezone.utc).isoformat()
        except (ValueError, OSError, OverflowError):
            return text

    def _text(self, value) -> str:
        return "" if value is None else str(value).strip()
