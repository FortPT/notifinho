"""Microsoft Teams Adaptive Card presentation for Proxmox VE events."""

from __future__ import annotations

from formatters.base import BaseFormatter
from models import Notification
from version import VERSION


class ProxmoxTeamsFormatter(BaseFormatter):
    def format(self, notification: Notification) -> dict:
        metadata = notification.metadata or {}
        icon, color, state = self._status(notification.status)
        title = notification.title or "Proxmox VE notification"
        facts = [
            self._fact("State", state),
            self._fact("Severity", self._label(metadata.get("severity"))),
            self._fact("Category", self._label(notification.category)),
            self._fact("Node", metadata.get("node") or metadata.get("host")),
            self._fact("VMID", metadata.get("vmid")),
            self._fact("Guest", metadata.get("guest")),
            self._fact("Job", metadata.get("job_id")),
            self._fact("Storage", metadata.get("storage")),
            self._fact(
                "Event time",
                self._format_datetime(
                    metadata.get("event_time") or notification.start_time
                ),
            ),
            self._fact("Duration", notification.duration),
        ]
        if notification.vm_total:
            facts.extend(
                (
                    self._fact("Guests OK", notification.vm_success),
                    self._fact("Guests failed", notification.vm_failed),
                )
            )
        if notification.failed_vms:
            facts.append(
                self._fact("Failed guests", ", ".join(notification.failed_vms))
            )
        if notification.errors:
            facts.append(
                self._fact("Error details", "; ".join(notification.errors))
            )
        if notification.successful_vms:
            facts.append(
                self._fact(
                    "Successful guests",
                    ", ".join(notification.successful_vms),
                )
            )
        body = [
            self._teams_header(f"🟧 {icon} {title}", color, "proxmox"),
            {
                "type": "TextBlock",
                "text": f"Proxmox VE • **{state}**",
                "isSubtle": True,
                "spacing": "Small",
                "wrap": True,
            },
            {
                "type": "Container",
                "style": "emphasis",
                "spacing": "Medium",
                "separator": True,
                "items": [
                    {
                        "type": "TextBlock",
                        "text": self._truncate(notification.body or title, 4000),
                        "weight": "Bolder",
                        "wrap": True,
                    }
                ],
            },
        ]
        facts = [fact for fact in facts if fact["value"]]
        if facts:
            body.append({"type": "FactSet", "spacing": "Medium", "facts": facts})
        body.append(
            {
                "type": "TextBlock",
                "text": f"FortPT Labs • Notifinho v{VERSION}",
                "isSubtle": True,
                "size": "Small",
                "separator": True,
                "wrap": True,
            }
        )
        return {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "msteams": {"width": "Full"},
                        "body": body,
                    },
                }
            ],
        }

    def _fact(self, title: str, value) -> dict:
        return {"title": title, "value": self._truncate(value, 1000)}

    @staticmethod
    def _status(value: str) -> tuple[str, str, str]:
        status = str(value or "").casefold()
        if status == "failure":
            return "🚨", "Attention", "Failed"
        if status == "warning":
            return "⚠️", "Warning", "Warning"
        if status == "success":
            return "✅", "Good", "Success"
        return "ℹ️", "Accent", "Information"

    @staticmethod
    def _label(value) -> str:
        return str(value or "").replace("_", " ").strip().title()
