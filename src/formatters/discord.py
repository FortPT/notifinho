"""Discord presentation for Xen Orchestra backup events."""

from __future__ import annotations

from config import config
from formatters.discord_common import DiscordCardData, DiscordCardFormatter, DiscordFact
from models import Notification


class DiscordFormatter(DiscordCardFormatter):
    """Format Xen Orchestra notifications using the shared Discord contract."""

    MAX_VMS = 10

    def format(self, notification: Notification) -> dict:
        status_text = self._status_text(notification.status)
        job_name = (
            notification.job_name
            or notification.title
            or notification.subject
            or "Xen Orchestra backup"
        )
        details = [
            DiscordFact("🧰", "Mode", notification.mode),
            DiscordFact("⏱️", "Duration", self._short_duration(notification.duration)),
            DiscordFact("📦", "Transfer size", notification.transfer_size),
            DiscordFact("💾", "Repository", notification.repository),
            DiscordFact("🚀", "Speed", notification.transfer_speed),
            DiscordFact("📊", "Result", self._result_text(notification), False),
            DiscordFact("▶️", "Started", self._format_datetime(notification.start_time)),
            DiscordFact("🏁", "Finished", self._format_datetime(notification.end_time)),
        ]
        if config.get("notifications", "xo", "show_ids", default=False):
            details.extend((
                DiscordFact("🆔", "Run ID", notification.run_id, False),
                DiscordFact("🆔", "Job ID", notification.job_id, False),
            ))
        self._add_vm_fact(details, "❌", "Failed VM", "Failed VMs", notification.failed_vms, notification, True)
        self._add_vm_fact(details, "⚠️", "Skipped VM", "Skipped VMs", notification.skipped_vms, notification, True)
        self._add_vm_fact(details, "✅", "Successful VM", "Successful VMs", notification.successful_vms, notification, False)

        message = notification.body or notification.title or notification.subject or status_text
        return self._render_discord_card(
            DiscordCardData(
                source="xo",
                integration="Xen Orchestra",
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
            )
        )

    @staticmethod
    def _status_text(status: str) -> str:
        value = str(status or "").casefold()
        if value in {"failure", "failed", "error"}:
            return "Backup Failure"
        if value in {"skipped", "warning"}:
            return "Backup Skipped"
        return "Backup Successful"

    def _result_text(self, notification: Notification) -> str:
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

    def _add_vm_fact(
        self,
        details: list[DiscordFact],
        icon: str,
        singular: str,
        plural: str,
        vms: list[str],
        notification: Notification,
        include_error: bool,
    ) -> None:
        if not vms:
            return
        details.append(
            DiscordFact(
                icon,
                singular if len(vms) == 1 else plural,
                self._format_vm_details(notification, vms, icon, include_error),
                False,
            )
        )

    def _format_vm_details(
        self,
        notification: Notification,
        vms: list[str],
        icon: str,
        include_error: bool,
    ) -> str:
        lines = []
        shown = vms[: self.MAX_VMS]
        for vm in shown:
            detail = notification.vm_details.get(vm, {}) or {}
            lines.append(f"{icon} **{vm}**")
            parts = []
            if detail.get("size"):
                parts.append(f"📦 {detail['size']}")
            if detail.get("speed"):
                parts.append(f"🚀 {detail['speed']}")
            repository = detail.get("repository")
            if repository and repository != notification.repository:
                parts.append(f"💾 {repository}")
            if parts:
                lines.append("└─ " + " • ".join(parts))
            if include_error and detail.get("error"):
                lines.append(f"└─ 🚨 {detail['error']}")
        remaining = len(vms) - len(shown)
        if remaining:
            lines.append(f"… and {remaining} more")
        return "\n".join(lines)

    @staticmethod
    def _short_duration(value: str) -> str:
        if not value:
            return ""
        return (
            value.replace(" minutes", " min")
            .replace(" minute", " min")
            .replace(" seconds", " sec")
            .replace(" second", " sec")
        )
