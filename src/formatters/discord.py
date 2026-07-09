"""
Notifinho

discord.py

Discord formatter.
"""

from __future__ import annotations

from datetime import datetime

from config import config
from models import Notification


class DiscordFormatter:

    MONTHS = {
        "January": "Jan",
        "February": "Feb",
        "March": "Mar",
        "April": "Apr",
        "May": "May",
        "June": "Jun",
        "July": "Jul",
        "August": "Aug",
        "September": "Sep",
        "October": "Oct",
        "November": "Nov",
        "December": "Dec",
    }

    XO_THUMBNAIL = "https://content.vates.tech/assets/xologoname.png"

    def format(
        self,
        notification: Notification,
    ) -> dict:

        status = notification.status.lower()

        if status == "failure":
            icon = "🚨"
            color = 0xE74C3C
            status_text = "Backup Failure"

        elif status == "skipped":
            icon = "⚠️"
            color = 0xF1C40F
            status_text = "Backup Skipped"

        else:
            icon = "✅"
            color = 0x2ECC71
            status_text = "Backup Successful"

        embed = {
            "title": f"{icon} {notification.job_name}",
            "description": f"Xen Orchestra • **{status_text}**",
            "color": color,
            "thumbnail": {
                "url": self.XO_THUMBNAIL,
            },
            "fields": [],
            "footer": {
                "text": "FortPT Labs\nNotifinho v1.0.0",
            },
        }

        #
        # Main backup info
        #

        embed["fields"].append({
            "name": "Mode",
            "value": notification.mode or "-",
            "inline": True,
        })

        embed["fields"].append({
            "name": "⏱ Duration",
            "value": self._short_duration(
                notification.duration,
            ),
            "inline": True,
        })

        embed["fields"].append({
            "name": "📦 Transfer",
            "value": notification.transfer_size or "-",
            "inline": True,
        })

        if notification.repository or notification.transfer_speed:

            embed["fields"].append({
                "name": "💾 Repository",
                "value": notification.repository or "-",
                "inline": True,
            })

            embed["fields"].append({
                "name": "🚀 Speed",
                "value": notification.transfer_speed or "-",
                "inline": True,
            })

            embed["fields"].append({
                "name": "\u200b",
                "value": "\u200b",
                "inline": True,
            })

        self._add_spacer(
            embed,
        )

        #
        # Result
        #

        result_parts = []

        if notification.vm_success:
            result_parts.append(
                f"✅ {notification.vm_success}"
            )

        if notification.vm_failed:
            result_parts.append(
                f"❌ {notification.vm_failed}"
            )

        if notification.vm_skipped:
            result_parts.append(
                f"⚠️ {notification.vm_skipped}"
            )

        embed["fields"].append({
            "name": "📊 Result",
            "value": " • ".join(result_parts) if result_parts else "-",
            "inline": False,
        })

        self._add_spacer(
            embed,
        )

        #
        # Failed VMs
        #

        if notification.failed_vms:

            embed["fields"].append({
                "name": "❌ Failed VM"
                if len(notification.failed_vms) == 1
                else "❌ Failed VMs",
                "value": self._format_vm_details(
                    notification,
                    notification.failed_vms,
                    include_error=True,
                ),
                "inline": False,
            })

            self._add_spacer(
                embed,
            )

        #
        # Skipped VMs
        #

        if notification.skipped_vms:

            embed["fields"].append({
                "name": "⚠️ Skipped VM"
                if len(notification.skipped_vms) == 1
                else "⚠️ Skipped VMs",
                "value": self._format_vm_details(
                    notification,
                    notification.skipped_vms,
                    include_error=True,
                ),
                "inline": False,
            })

            self._add_spacer(
                embed,
            )

        #
        # Successful VMs
        #

        if notification.successful_vms:

            embed["fields"].append({
                "name": "✅ Successful VM"
                if len(notification.successful_vms) == 1
                else "✅ Successful VMs",
                "value": self._format_vm_details(
                    notification,
                    notification.successful_vms,
                    include_error=False,
                ),
                "inline": False,
            })

            self._add_spacer(
                embed,
            )

        #
        # Times
        #

        if notification.start_time:

            embed["fields"].append({
                "name": "🕒 Started",
                "value": self._format_datetime(
                    notification.start_time,
                ),
                "inline": True,
            })

        if notification.end_time:

            embed["fields"].append({
                "name": "🏁 Finished",
                "value": self._format_datetime(
                    notification.end_time,
                ),
                "inline": True,
            })

        #
        # Optional IDs
        #

        show_ids = config.get(
            "notifications",
            "xo",
            "show_ids",
            default=False,
        )

        if show_ids:

            self._add_spacer(
                embed,
            )

            if notification.run_id:

                embed["fields"].append({
                    "name": "Run ID",
                    "value": notification.run_id,
                    "inline": False,
                })

            if notification.job_id:

                embed["fields"].append({
                    "name": "Job ID",
                    "value": notification.job_id,
                    "inline": False,
                })

        return {
            "embeds": [
                embed,
            ],
        }

    def _add_spacer(
        self,
        embed: dict,
    ) -> None:

        embed["fields"].append({
            "name": "\u200b",
            "value": "\u200b",
            "inline": False,
        })

    def _format_vm_details(
        self,
        notification: Notification,
        vms: list[str],
        include_error: bool,
    ) -> str:

        lines = []

        shown = vms[:10]

        for vm in shown:

            details = notification.vm_details.get(
                vm,
                {},
            )

            lines.append(
                f"**{vm}**"
            )

            size = details.get(
                "size",
                "",
            )

            speed = details.get(
                "speed",
                "",
            )

            error = details.get(
                "error",
                "",
            )

            detail_parts = []

            if size:

                detail_parts.append(
                    f"📦 {size}"
                )

            if speed:

                detail_parts.append(
                    f"🚀 {speed}"
                )

            if include_error and error:

                detail_parts.append(
                    f"🚨 {error}"
                )

            if detail_parts:

                lines.append(
                    "└─ " + " • ".join(detail_parts)
                )

            lines.append("")

        remaining = len(vms) - len(shown)

        if remaining > 0:

            lines.append(
                f"... and {remaining} more"
            )

        return "\n".join(lines).strip()

    def _short_duration(
        self,
        value: str,
    ) -> str:

        if not value:

            return "-"

        return (
            value
            .replace(" minutes", " min")
            .replace(" minute", " min")
            .replace(" seconds", " sec")
            .replace(" second", " sec")
        )

    def _format_datetime(
        self,
        value: str,
    ) -> str:

        if not value:

            return ""

        cleaned = value

        cleaned = cleaned.replace("1st", "1")
        cleaned = cleaned.replace("2nd", "2")
        cleaned = cleaned.replace("3rd", "3")
        cleaned = cleaned.replace("th", "")

        for full, short in self.MONTHS.items():

            cleaned = cleaned.replace(
                full,
                short,
            )

        for fmt in (
            "%A, %b %d %Y, %I:%M:%S %p",
            "%A, %b %d %Y, %I:%M %p",
        ):

            try:

                parsed = datetime.strptime(
                    cleaned,
                    fmt,
                )

                return parsed.strftime(
                    "%d %b %Y • %H:%M",
                )

            except ValueError:

                continue

        return value
