"""Discord presentation for normalized Proxmox VE events."""

from __future__ import annotations

from formatters.discord_common import DiscordCardData, DiscordCardFormatter, DiscordFact
from models import Notification


class ProxmoxDiscordFormatter(DiscordCardFormatter):
    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        title = notification.title or "Proxmox VE notification"
        details = [
            DiscordFact("🆔", "VMID", metadata.get("vmid")),
            DiscordFact("💻", "Guest", metadata.get("guest")),
            DiscordFact("🧰", "Job", metadata.get("job_id")),
            DiscordFact("💾", "Storage", metadata.get("storage")),
            DiscordFact("⏱️", "Duration", notification.duration),
        ]
        if notification.vm_total:
            details.extend((
                DiscordFact("✅", "Guests OK", notification.vm_success),
                DiscordFact("❌", "Guests failed", notification.vm_failed),
            ))
        if notification.failed_vms:
            details.append(DiscordFact("❌", "Failed guests", "\n".join(notification.failed_vms), False))
        if notification.errors:
            details.append(DiscordFact("🧯", "Error details", "\n".join(notification.errors), False))
        if notification.successful_vms:
            details.append(DiscordFact("✅", "Successful guests", "\n".join(notification.successful_vms), False))
        device = metadata.get("node") or metadata.get("host") or metadata.get("guest") or "Proxmox"
        return self._render_discord_card(
            DiscordCardData(
                source="proxmox",
                integration="Proxmox VE",
                device=device,
                event=title,
                message=notification.body or title,
                status=notification.status,
                severity=metadata.get("severity") or notification.status,
                category=notification.category or "virtualization",
                source_area=metadata.get("node") or "Virtualization",
                event_time=metadata.get("event_time") or notification.start_time,
                device_icon="🟧",
                source_area_icon="🖥️",
                details=tuple(details),
            )
        )
