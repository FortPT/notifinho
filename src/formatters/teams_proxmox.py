"""Microsoft Teams Adaptive Card presentation for Proxmox VE events."""

from __future__ import annotations

from formatters.teams_common import TeamsCardData, TeamsCardFormatter, TeamsFact
from models import Notification


class ProxmoxTeamsFormatter(TeamsCardFormatter):
    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        title = notification.title or "Proxmox VE notification"
        details = [
            TeamsFact("🆔", "VMID", metadata.get("vmid")),
            TeamsFact("💻", "Guest", metadata.get("guest")),
            TeamsFact("🧰", "Job", metadata.get("job_id")),
            TeamsFact("💾", "Storage", metadata.get("storage")),
            TeamsFact("⏱️", "Duration", notification.duration),
        ]
        if notification.vm_total:
            details.extend(
                (
                    TeamsFact("✅", "Guests OK", notification.vm_success),
                    TeamsFact("❌", "Guests failed", notification.vm_failed),
                )
            )
        if notification.failed_vms:
            details.append(
                TeamsFact("❌", "Failed guests", ", ".join(notification.failed_vms))
            )
        if notification.errors:
            details.append(
                TeamsFact("🧯", "Error details", "; ".join(notification.errors))
            )
        if notification.successful_vms:
            details.append(
                TeamsFact(
                    "✅",
                    "Successful guests",
                    ", ".join(notification.successful_vms),
                ),
            )
        device = metadata.get("node") or metadata.get("host") or metadata.get("guest") or "Proxmox"
        return self._render_teams_card(
            TeamsCardData(
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
                event_icon="🔔",
                details=tuple(details),
            )
        )
