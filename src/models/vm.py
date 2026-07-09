"""
Notifinho

vm.py

Represents one VM inside a backup report.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VM:

    #
    # VM
    #

    name: str = ""

    description: str = ""

    uuid: str = ""

    pool_id: str = ""

    #
    # Result
    #

    status: str = ""

    retry: bool = False

    #
    # Timing
    #

    start_time: str = ""

    end_time: str = ""

    duration: str = ""

    #
    # Transfer
    #

    size: str = ""

    speed: str = ""

    #
    # Error
    #

    error: str = ""
