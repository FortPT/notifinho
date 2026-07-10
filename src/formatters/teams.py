"""
Notifinho

teams.py

Microsoft Teams Adaptive Card formatter.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from config import config
from formatters.base import BaseFormatter
from models import Notification


class TeamsFormatter(BaseFormatter):
    """
    Format notifications as Microsoft Teams Adaptive Cards.
    """

    MAX_VMS = 12

    def format(
        self,
        notification: Notification,
    ) -> dict[str, Any]:

        icon, color, status_text = self._status_meta(
            notification.status,
        )

        title = (
            notification.job_name
            or notification.title
            or notification.subject
            or "Notification"
        )

        source_name = self._source_name(
            notification.source,
        )

        body = [
            {
                "type": "TextBlock",
                "text": f"{icon} {title}",
                "weight": "Bolder",
                "size": "Large",
                "color": color,
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": f"{source_name} • **{status_text}**",
                "isSubtle": True,
                "spacing": "Small",
                "wrap": True,
            },
        ]

        facts = []

        self._add_fact(
            facts,
            "Mode",
            notification.mode,
        )

        self._add_fact(
            facts,
            "Duration",
            self._short_duration(notification.duration),
        )

        self._add_fact(
            facts,
            "Transfer",
            notification.transfer_size,
        )

        self._add_fact(
            facts,
            "Repository",
            notification.repository,
        )

        self._add_fact(
            facts,
            "Speed",
            notification.transfer_speed,
        )

        self._add_fact(
            facts,
            "Result",
            self._result_text(notification),
        )

        if notification.start_time:

            self._add_fact(
                facts,
                "Started",
                self._format_datetime(notification.start_time),
            )

        if notification.end_time:

            self._add_fact(
                facts,
                "Finished",
                self._format_datetime(notification.end_time),
            )

        show_ids = config.get(
            "notifications",
            "xo",
            "show_ids",
            default=False,
        )

        if show_ids:

            self._add_fact(
                facts,
                "Run ID",
                notification.run_id,
            )

            self._add_fact(
                facts,
                "Job ID",
                notification.job_id,
            )

        if facts:

            body.append(
                {
                    "type": "FactSet",
                    "spacing": "Medium",
                    "facts": facts,
                }
            )

        self._add_vm_section(
            body,
            singular="❌ Failed VM",
            plural="❌ Failed VMs",
            icon="❌",
            vms=notification.failed_vms,
            notification=notification,
            include_error=True,
            separator=True,
        )

        self._add_vm_section(
            body,
            singular="⚠️ Skipped VM",
            plural="⚠️ Skipped VMs",
            icon="⚠️",
            vms=notification.skipped_vms,
            notification=notification,
            include_error=True,
            separator=True,
        )

        self._add_vm_section(
            body,
            singular="✅ Successful VM",
            plural="✅ Successful VMs",
            icon="✅",
            vms=notification.successful_vms,
            notification=notification,
            include_error=False,
            separator=True,
        )

        card = {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.4",
            "msteams": {
                "width": "Full",
            },
            "body": body,
        }

        return {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": card,
                }
            ],
        }

    def _status_meta(
        self,
        status: str,
    ) -> tuple[str, str, str]:

        normalized = (status or "").lower()

        if normalized in ("failure", "failed", "error"):

            return "🚨", "Attention", "Backup Failure"

        if normalized in ("skipped", "warning"):

            return "⚠️", "Warning", "Backup Skipped"

        return "✅", "Good", "Backup Successful"

    def _source_name(
        self,
        source: str,
    ) -> str:

        normalized = (source or "").lower()

        if normalized == "xo":

            return "Xen Orchestra"

        if normalized == "zabbix":

            return "Zabbix"

        if normalized == "truenas":

            return "TrueNAS"

        if normalized == "proxmox":

            return "Proxmox"

        return source or "Notifinho"

    def _add_fact(
        self,
        facts: list[dict[str, str]],
        title: str,
        value,
    ) -> None:

        if value is None:

            return

        value = str(value).strip()

        if not value or value == "-":

            return

        facts.append(
            {
                "title": f"{title}:",
                "value": value,
            }
        )

    def _result_text(
        self,
        notification: Notification,
    ) -> str:

        success = notification.vm_success or notification.successes

        failed = notification.vm_failed or notification.failures

        skipped = notification.vm_skipped or notification.skipped

        parts = []

        if success:

            parts.append(f"✅ {success}")

        if failed:

            parts.append(f"❌ {failed}")

        if skipped:

            parts.append(f"⚠️ {skipped}")

        return " • ".join(parts) if parts else "-"

    def _add_vm_section(
        self,
        body: list[dict[str, Any]],
        singular: str,
        plural: str,
        icon: str,
        vms: list[str],
        notification: Notification,
        include_error: bool,
        separator: bool = False,
    ) -> None:

        if not vms:

            return

        title = singular if len(vms) == 1 else plural

        body.append(
            {
                "type": "TextBlock",
                "text": title,
                "weight": "Bolder",
                "spacing": "Medium",
                "separator": separator,
                "wrap": True,
            }
        )

        body.append(
            {
                "type": "TextBlock",
                "text": self._format_vm_details(
                    notification=notification,
                    vms=vms,
                    icon=icon,
                    include_error=include_error,
                ),
                "wrap": True,
                "spacing": "Small",
            }
        )

    def _format_vm_details(
        self,
        notification: Notification,
        vms: list[str],
        icon: str,
        include_error: bool,
    ) -> str:

        lines = []

        shown_vms = vms[: self.MAX_VMS]

        for vm in shown_vms:

            details = notification.vm_details.get(vm, {}) or {}

            lines.append(f"{icon} **{vm}**")

            metadata = []

            size = details.get("size")

            speed = details.get("speed")

            repository = details.get("repository")

            error = details.get("error")

            if size:

                metadata.append(f"📦 {size}")

            if speed:

                metadata.append(f"🚀 {speed}")

            if repository and repository != notification.repository:

                metadata.append(f"💾 {repository}")

            if metadata:

                lines.append(f"└─ {' • '.join(metadata)}")

            if include_error and error:

                lines.append(f"└─ 🚨 {error}")

        remaining = len(vms) - len(shown_vms)

        if remaining > 0:

            lines.append(f"...and {remaining} more.")

        return "\n".join(lines) if lines else "-"

    def _short_duration(
        self,
        value: str,
    ) -> str:

        if not value:

            return "-"

        value = str(value).strip()

        replacements = {
            " hours": " h",
            " hour": " h",
            " minutes": " min",
            " minute": " min",
            " seconds": " s",
            " second": " s",
        }

        for old, new in replacements.items():

            value = value.replace(old, new)

        return value

    def _remove_ordinal_suffixes(
        self,
        value: str,
    ) -> str:

        for day in range(1, 32):

            for suffix in ("st", "nd", "rd", "th"):

                value = value.replace(
                    f"{day}{suffix}",
                    str(day),
                )

        return value

    def _format_datetime(
        self,
        value: str,
    ) -> str:

        if not value:

            return "-"

        value = str(value).strip()

        value = self._remove_ordinal_suffixes(
            value,
        )

        value = value.replace(
            " am",
            " AM",
        ).replace(
            " pm",
            " PM",
        )

        formats = [
            "%A, %B %d %Y, %I:%M:%S %p",
            "%A, %B %d %Y, %I:%M %p",
            "%B %d, %Y at %I:%M %p",
            "%B %d, %Y %I:%M %p",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
        ]

        for fmt in formats:

            try:

                parsed = datetime.strptime(
                    value,
                    fmt,
                )

                return parsed.strftime(
                    "%d/%m/%y %H:%M",
                )

            except ValueError:

                continue

        return value
