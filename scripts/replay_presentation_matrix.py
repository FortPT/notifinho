#!/usr/bin/env python3
"""Render or send one private-safe presentation sample per source."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from models import Notification  # noqa: E402
from formatters.discord import DiscordFormatter  # noqa: E402
from formatters.discord_grafana import GrafanaDiscordFormatter  # noqa: E402
from formatters.discord_portainer import PortainerDiscordFormatter  # noqa: E402
from formatters.discord_proxmox import ProxmoxDiscordFormatter  # noqa: E402
from formatters.discord_qnap import QNAPDiscordFormatter  # noqa: E402
from formatters.discord_synology import SynologyDiscordFormatter  # noqa: E402
from formatters.discord_truenas import TrueNASDiscordFormatter  # noqa: E402
from formatters.discord_unifi import (  # noqa: E402
    UniFiDriveDiscordFormatter,
    UniFiNetworkDiscordFormatter,
    UniFiProtectDiscordFormatter,
)
from formatters.discord_zabbix import ZabbixDiscordFormatter  # noqa: E402
from formatters.teams import TeamsFormatter  # noqa: E402
from formatters.teams_grafana import GrafanaTeamsFormatter  # noqa: E402
from formatters.teams_portainer import PortainerTeamsFormatter  # noqa: E402
from formatters.teams_proxmox import ProxmoxTeamsFormatter  # noqa: E402
from formatters.teams_qnap import QNAPTeamsFormatter  # noqa: E402
from formatters.teams_synology import SynologyTeamsFormatter  # noqa: E402
from formatters.teams_truenas import TrueNASTeamsFormatter  # noqa: E402
from formatters.teams_unifi import (  # noqa: E402
    UniFiDriveTeamsFormatter,
    UniFiNetworkTeamsFormatter,
    UniFiProtectTeamsFormatter,
)
from formatters.teams_zabbix import ZabbixTeamsFormatter  # noqa: E402


SOURCES = (
    "xo",
    "zabbix",
    "qnap",
    "grafana",
    "truenas",
    "unifi_network",
    "unifi_protect",
    "unifi_drive",
    "portainer",
    "proxmox",
    "synology",
)

DISCORD_FORMATTERS = {
    "xo": DiscordFormatter(),
    "zabbix": ZabbixDiscordFormatter(),
    "qnap": QNAPDiscordFormatter(),
    "grafana": GrafanaDiscordFormatter(),
    "truenas": TrueNASDiscordFormatter(),
    "unifi_network": UniFiNetworkDiscordFormatter(),
    "unifi_protect": UniFiProtectDiscordFormatter(),
    "unifi_drive": UniFiDriveDiscordFormatter(),
    "portainer": PortainerDiscordFormatter(),
    "proxmox": ProxmoxDiscordFormatter(),
    "synology": SynologyDiscordFormatter(),
}

TEAMS_FORMATTERS = {
    "xo": TeamsFormatter(),
    "zabbix": ZabbixTeamsFormatter(),
    "qnap": QNAPTeamsFormatter(),
    "grafana": GrafanaTeamsFormatter(),
    "truenas": TrueNASTeamsFormatter(),
    "unifi_network": UniFiNetworkTeamsFormatter(),
    "unifi_protect": UniFiProtectTeamsFormatter(),
    "unifi_drive": UniFiDriveTeamsFormatter(),
    "portainer": PortainerTeamsFormatter(),
    "proxmox": ProxmoxTeamsFormatter(),
    "synology": SynologyTeamsFormatter(),
}


def build_notification(source: str) -> Notification:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    timestamp = now.isoformat().replace("+00:00", "Z")
    item = Notification(
        source=source,
        category="storage",
        status="warning",
        title=f"Synthetic {source.replace('_', ' ').title()} presentation warning",
        body="Private-safe v1.8.1 presentation validation event.",
        job_name="Synthetic Xen Orchestra presentation backup",
        repository="SYNTHETIC-REPOSITORY",
        start_time=timestamp,
        duration="5 min",
        vm_total=2,
        vm_success=1,
        vm_failed=1,
        successful_vms=["SYNTHETIC-VM-OK"],
        failed_vms=["SYNTHETIC-VM-FAILED"],
        errors=["Synthetic validation error"],
    )
    item.metadata = {
        "host": "SYNTHETIC-HOST",
        "hostname": "SYNTHETIC-HOST",
        "problem_name": "Synthetic Zabbix problem",
        "severity": "warning",
        "event_time": timestamp,
        "nas_name": "SYNTHETIC-NAS",
        "application": "Synthetic application",
        "event_type": "storage warning",
        "message": item.body,
        "alert_name": "Synthetic Grafana alert",
        "state": "warning",
        "alert_count": 1,
        "alerts": [{"event_type": "new", "message": item.body}],
        "controller": "SYNTHETIC-CONTROLLER",
        "client_display_name": "SYNTHETIC-CLIENT",
        "wifi_name": "SYNTHETIC-WIFI",
        "trigger_key": "motion",
        "trigger_device": "SYNTHETIC-CAMERA",
        "alarm_name": "Notifinho v1.8.1 presentation validation",
        "system": "SYNTHETIC-DRIVE",
        "backup_task": "SYNTHETIC-BACKUP",
        "instance": "SYNTHETIC-PORTAINER",
        "alert_source": "portainer",
        "node": "SYNTHETIC-PVE",
        "storage": "SYNTHETIC-STORAGE",
        "model": "SYNTHETIC-MODEL",
        "storage_pool": "SYNTHETIC-POOL",
    }
    return item


def render(sources: list[str], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for source in sources:
        item = build_notification(source)
        discord_formatter = DISCORD_FORMATTERS[source]
        teams_formatter = TEAMS_FORMATTERS[source]
        payload = {
            "source": source,
            "discord": discord_formatter._sanitize_payload(
                discord_formatter.format(item)
            ),
            "teams": teams_formatter._sanitize_payload(
                teams_formatter.format(item)
            ),
        }
        destination = output_dir / f"{source}.json"
        destination.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"rendered={destination}")


def send(sources: list[str], confirmed: bool) -> None:
    if not confirmed:
        raise SystemExit("Sending requires --confirm-send.")
    # Router imports the application logger and is intentionally loaded only
    # for confirmed delivery inside a running Notifinho container.
    from router import Router

    router = Router()
    failures = []
    for source in sources:
        delivered = router.route(build_notification(source))
        print(f"source={source} delivered={str(delivered).lower()}")
        if not delivered:
            failures.append(source)
    if failures:
        raise SystemExit("undelivered_sources=" + ",".join(failures))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=("render", "send"),
        default="render",
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        choices=SOURCES,
        default=list(SOURCES),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/tmp/notifinho-v181-card-previews"),
    )
    parser.add_argument("--confirm-send", action="store_true")
    args = parser.parse_args()

    if args.mode == "render":
        render(args.sources, args.output_dir)
    else:
        send(args.sources, args.confirm_send)


if __name__ == "__main__":
    main()
