"""
Notifinho

teams.py

Microsoft Teams Adaptive Card formatter.
"""

from __future__ import annotations

from typing import Any

from config import config
from formatters.teams_common import TeamsCardData, TeamsCardFormatter, TeamsFact
from models import Notification


class TeamsFormatter(TeamsCardFormatter):
    """
    Format notifications as Microsoft Teams Adaptive Cards.
    """

    MAX_VMS = 12

    def format(
        self,
        notification: Notification,
    ) -> dict[str, Any]:
        _icon, _color, status_text = self._status_meta(
            notification.status,
        )
        job_name = (
            notification.job_name
            or notification.title
            or notification.subject
            or "Notification"
        )
        source_name = self._source_name(
            notification.source,
        )
        details = [
            TeamsFact("🧰", "Mode", notification.mode),
            TeamsFact("⏱️", "Duration", self._short_duration(notification.duration)),
            TeamsFact("📦", "Transfer size", notification.transfer_size),
            TeamsFact("💾", "Repository", notification.repository),
            TeamsFact("🚀", "Speed", notification.transfer_speed),
            TeamsFact("📊", "Result", self._result_text(notification)),
            TeamsFact("▶️", "Started", self._format_datetime(notification.start_time)),
            TeamsFact("🏁", "Finished", self._format_datetime(notification.end_time)),
        ]
        show_ids = config.get(
            "notifications",
            "xo",
            "show_ids",
            default=False,
        )
        if show_ids:
            details.extend(
                (
                    TeamsFact("🆔", "Run ID", notification.run_id),
                    TeamsFact("🆔", "Job ID", notification.job_id),
                )
            )
        extra_body = []
        self._add_vm_section(
            extra_body,
            singular="❌ Failed VM",
            plural="❌ Failed VMs",
            icon="❌",
            vms=notification.failed_vms,
            notification=notification,
            include_error=True,
            separator=True,
        )
        self._add_vm_section(
            extra_body,
            singular="⚠️ Skipped VM",
            plural="⚠️ Skipped VMs",
            icon="⚠️",
            vms=notification.skipped_vms,
            notification=notification,
            include_error=True,
            separator=True,
        )
        self._add_vm_section(
            extra_body,
            singular="✅ Successful VM",
            plural="✅ Successful VMs",
            icon="✅",
            vms=notification.successful_vms,
            notification=notification,
            include_error=False,
            separator=True,
        )
        message = notification.body or notification.title or notification.subject or status_text
        return self._render_teams_card(
            TeamsCardData(
                source="xo",
                integration=source_name,
                device=job_name,
                event=status_text,
                message=message,
                status=notification.status,
                state=status_text,
                severity=notification.status,
                category=notification.category or "backup",
                source_area=notification.repository or "Backup",
                event_time=notification.end_time or notification.start_time,
                device_icon="🗄️",
                source_area_icon="💾",
                event_icon="📋",
                details=tuple(details),
                extra_body=tuple(extra_body),
            )
        )

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

    def _result_text(
        self,
        notification: Notification,
    ) -> str:

        success = notification.vm_success or notification.successes

        failed = notification.vm_failed or notification.failures

        skipped = notification.vm_skipped or notification.skipped

        total = notification.vm_total or success + failed + skipped

        if not total:

            return ""

        parts = [f"✅ {success} of {total} VMs successful"]

        if failed:

            parts.append(f"❌ {failed} failed")

        if skipped:

            parts.append(f"⚠️ {skipped} skipped")

        return " • ".join(parts)

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

            return ""

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
