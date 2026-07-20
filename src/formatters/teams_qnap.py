"""Microsoft Teams Adaptive Card formatter for QNAP events."""

from __future__ import annotations

import re
from typing import Any

from formatters.teams_common import (
    TeamsCardData,
    TeamsCardFormatter,
    TeamsFact,
)
from models import Notification


class QNAPTeamsFormatter(TeamsCardFormatter):
    """Format QNAP events as polished Microsoft Teams Adaptive Cards."""

    NAS_ICON = "🗄️"

    CATEGORY_ICONS = {
        "storage": "💾",
        "security": "🛡️",
        "backup": "🔄",
        "system": "⚙️",
        "power": "🔌",
        "network": "🌐",
        "update": "⬆️",
        "application": "🧩",
        "generic": "🔔",
    }

    OPERATIONAL_KEYS = (
        "event_type",
        "storage_pool",
        "pool",
        "volume",
        "raid_group",
        "raid_level",
        "disk",
        "disk_name",
        "drive",
        "drive_bay",
        "smart_status",
        "backup_job",
        "job_name",
        "task",
        "destination",
        "repository",
        "ups_status",
        "battery_level",
        "battery_capacity",
        "runtime_remaining",
        "power_source",
        "user",
        "username",
        "account",
        "source_ip",
        "ip_address",
        "protocol",
        "firmware_version",
        "current_version",
        "new_version",
        "available_version",
        "connection_type",
        "power_event",
    )

    IGNORED_SOURCE_FIELDS = {
        "app",
        "applicationname",
        "application",
        "appname",
        "category",
        "content",
        "date",
        "dateandtime",
        "datetime",
        "description",
        "detail",
        "details",
        "eventcategory",
        "eventmessage",
        "eventtime",
        "host",
        "message",
        "nasname",
        "notificationcategory",
        "severity",
        "sourcefields",
        "subject",
        "time",
        "timestamp",
        "thisisatestmessagefromnas",
    }

    FIELD_ICONS = {
        "application": "📦",
        "eventtype": "🏷️",
        "storagepool": "💾",
        "pool": "💾",
        "volume": "💿",
        "raidgroup": "🧱",
        "raidlevel": "🧱",
        "disk": "💽",
        "diskname": "💽",
        "drive": "💽",
        "drivebay": "🗃️",
        "smartstatus": "🩺",
        "backupjob": "🔄",
        "jobname": "🔄",
        "task": "📋",
        "destination": "🎯",
        "repository": "🗂️",
        "upsstatus": "🔋",
        "batterylevel": "🔋",
        "batterycapacity": "🔋",
        "runtimeremaining": "⏳",
        "powersource": "⚡",
        "powerevent": "⚡",
        "user": "👤",
        "username": "👤",
        "account": "👤",
        "sourceip": "🌐",
        "ipaddress": "🌐",
        "protocol": "🔗",
        "connectiontype": "🔗",
        "firmwareversion": "🧩",
        "currentversion": "📌",
        "newversion": "⬆️",
        "availableversion": "⬆️",
    }

    def format(self, notification: Notification) -> dict[str, Any]:
        metadata = notification.metadata or {}
        nas_name = self._text(
            metadata.get("nas_name")
            or metadata.get("host")
            or "QNAP NAS"
        )
        category_value = (
            metadata.get("category")
            or notification.category
            or "generic"
        )
        category_key = self._category_key(category_value)
        category = self._label(category_value)
        category_icon = self.CATEGORY_ICONS.get(
            category_key,
            self.CATEGORY_ICONS["generic"],
        )
        severity = self._text(
            metadata.get("severity")
            or notification.status
            or "information"
        )
        _status_icon, _accent_color, status_text = self._status_meta(
            notification.status,
            severity,
        )
        message = self._text(
            metadata.get("message")
            or notification.body
            or notification.title
            or notification.subject
            or "QNAP notification"
        )
        application = self._text(metadata.get("application"))
        event_time = self._text(
            metadata.get("event_time")
            or notification.start_time
            or notification.end_time
        )
        event_type = self._text(metadata.get("event_type"))
        event_label = self._label(event_type) if event_type else "QNAP event"
        event = (
            application
            if category_key == "update" and application
            else event_label
        )
        event_icon = self._event_icon(
            event_type or event,
            category_key,
            notification.status,
            severity,
        )

        details: list[TeamsFact] = []
        if application and application.casefold() != event.casefold():
            details.append(TeamsFact("📦", "Application", application))
        for label, value in self._operational_fields(metadata)[:15]:
            icon, clean_label = self._split_icon_label(label)
            details.append(TeamsFact(icon, clean_label, value))

        return self._render_teams_card(
            TeamsCardData(
                source="qnap",
                integration="QNAP",
                device=nas_name,
                event=event,
                message=message,
                status=notification.status,
                state=status_text,
                severity=severity,
                category=category,
                source_area=category,
                source_area_icon=category_icon,
                event_time=event_time,
                device_icon=self.NAS_ICON,
                event_icon=event_icon,
                details=tuple(details),
            )
        )

    def _status_meta(self, status: str, severity: str) -> tuple[str, str, str]:
        status_value = str(status or "").strip().lower()
        severity_value = str(severity or "").strip().lower()
        failure = {
            "critical", "danger", "disaster", "emergency", "error",
            "failed", "failure", "high",
        }
        warning = {
            "alert", "average", "degraded", "medium", "warn", "warning",
        }
        success = {
            "normal", "ok", "recovered", "resolved", "success", "successful",
        }
        information = {"information", "informational", "info", "notice"}

        if status_value in failure:
            return "🚨", "Attention", "Failure"
        if status_value in warning:
            return "⚠️", "Warning", "Warning"
        if status_value in success:
            return "✅", "Good", "Success"
        if status_value in information:
            return "ℹ️", "Accent", "Information"
        if severity_value in failure:
            return "🚨", "Attention", "Failure"
        if severity_value in warning:
            return "⚠️", "Warning", "Warning"
        if severity_value in success:
            return "✅", "Good", "Success"
        if severity_value in information | {"low"}:
            return "ℹ️", "Accent", "Information"
        return "🔔", "Default", self._label(status_value or "information")

    def _event_icon(
        self,
        event_type: str,
        category_key: str,
        status: str,
        severity: str,
    ) -> str:
        event_key = self._normalize_key(event_type)
        if "test" in event_key:
            return "🧪"
        if any(token in event_key for token in ("failed", "failure", "error", "critical")):
            return "❌"
        if any(token in event_key for token in ("warning", "alert", "degraded")):
            return "⚠️"
        if any(token in event_key for token in ("resolved", "recovered", "success", "normal")):
            return "✅"

        keyword_icons = (
            (("backup", "sync", "hbs"), "🔄"),
            (("storage", "pool", "raid", "volume"), "💾"),
            (("smart", "disk", "drive"), "🩺"),
            (("login", "security", "auth", "account"), "🛡️"),
            (("ups", "power", "battery"), "🔋"),
            (("firmware", "update", "version"), "⬆️"),
            (("network", "connection", "ip"), "🌐"),
        )
        for keywords, icon in keyword_icons:
            if any(keyword in event_key for keyword in keywords):
                return icon

        status_icon, _, _ = self._status_meta(status, severity)
        return self.CATEGORY_ICONS.get(category_key, status_icon)

    def _operational_fields(self, metadata: dict) -> list[tuple[str, str]]:
        values: list[tuple[str, str]] = []
        seen: set[str] = set()

        for key in self.OPERATIONAL_KEYS:
            value = self._text(metadata.get(key))
            if not value:
                continue
            if key == "event_type":
                value = self._label(value)
            values.append((self._field_label(key), value))
            seen.add(self._normalize_key(key))

        source_fields = metadata.get("source_fields", {})
        if not isinstance(source_fields, dict):
            return values

        for key, raw_value in source_fields.items():
            normalized_key = self._normalize_key(key)
            if normalized_key in self.IGNORED_SOURCE_FIELDS or normalized_key in seen:
                continue
            value = self._text(raw_value)
            if not value:
                continue
            values.append((self._field_label(key), value))
            seen.add(normalized_key)

        return values

    def _field_label(self, key) -> str:
        normalized_key = self._normalize_key(key)
        icon = self.FIELD_ICONS.get(normalized_key, "🔹")
        return f"{icon} {self._label(key)}"

    @staticmethod
    def _split_icon_label(value: str) -> tuple[str, str]:
        icon, separator, label = str(value or "").partition(" ")
        return (icon or "🔹", label if separator else icon)

    def _category_key(self, value) -> str:
        normalized = self._normalize_key(value)
        aliases = (
            (("storage", "disk", "raid", "volume", "snapshot"), "storage"),
            (("security", "login", "auth", "account"), "security"),
            (("backup", "hbs", "sync", "replication"), "backup"),
            (("power", "ups", "battery"), "power"),
            (("network", "connection", "ethernet", "wifi"), "network"),
            (("firmware", "update", "upgrade"), "update"),
            (("application", "app"), "application"),
            (("system",), "system"),
        )
        for keywords, category_key in aliases:
            if any(keyword in normalized for keyword in keywords):
                return category_key
        return "generic"

    def _normalize_key(self, value) -> str:
        return re.sub(r"[^a-z0-9]", "", str(value or "").lower())

    def _label(self, value) -> str:
        words = re.sub(r"[_-]+", " ", str(value or "").strip()).split()
        acronyms = {
            "hbs": "HBS",
            "hdd": "HDD",
            "id": "ID",
            "ip": "IP",
            "nas": "NAS",
            "qnap": "QNAP",
            "qts": "QTS",
            "raid": "RAID",
            "smart": "SMART",
            "ssd": "SSD",
            "ups": "UPS",
            "usb": "USB",
        }
        return " ".join(
            acronyms.get(word.lower(), word.capitalize())
            for word in words
        ) or "Generic"

    def _text(self, value) -> str:
        if value is None:
            return ""
        if isinstance(value, dict):
            parts = []
            for key, nested_value in value.items():
                nested_text = self._text(nested_value)
                if nested_text:
                    parts.append(f"{self._label(key)}: {nested_text}")
            return ", ".join(parts)
        if isinstance(value, (list, tuple, set)):
            return ", ".join(
                text
                for item in value
                if (text := self._text(item))
            )
        return str(value).strip()

QnapTeamsFormatter = QNAPTeamsFormatter
