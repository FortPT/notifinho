"""
Notifinho

notification.py

Core notification model.

Every parser should populate this object.
Every formatter should consume this object.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Notification:
    """
    Generic notification exchanged between all
    application components.
    """

    #
    # Source
    #

    source: str = ""
    category: str = ""
    status: str = ""

    #
    # Message
    #

    title: str = ""
    subject: str = ""
    body: str = ""
    sender: str = ""

    #
    # Job information
    #

    job_name: str = ""
    job_id: str = ""
    run_id: str = ""
    mode: str = ""

    #
    # Backup target / transfer
    #

    repository: str = ""
    transfer_size: str = ""
    transfer_speed: str = ""

    #
    # Timing
    #

    start_time: str = ""
    end_time: str = ""
    duration: str = ""

    #
    # Statistics
    #

    vm_total: int = 0
    vm_success: int = 0
    vm_failed: int = 0
    vm_skipped: int = 0

    #
    # VM Lists
    #

    successful_vms: list[str] = field(default_factory=list)
    failed_vms: list[str] = field(default_factory=list)
    skipped_vms: list[str] = field(default_factory=list)

    #
    # Per-VM details
    #
    # Example:
    # {
    #   "VM-11 | Home Assistant": {
    #       "error": "Body Timeout Error",
    #       "repository": "UNAS-01 | NFS | Critical Backups",
    #       "speed": "13.39 MiB/s",
    #       "size": "8.27 GiB"
    #   }
    # }
    #

    vm_details: dict = field(default_factory=dict)

    #
    # Error Information
    #

    error: str = ""
    errors: list[str] = field(default_factory=list)

    #
    # Compatibility fields
    #

    successes: int = 0
    failures: int = 0
    skipped: int = 0

    #
    # Raw Data
    #

    metadata: dict = field(default_factory=dict)
    items: list = field(default_factory=list)
