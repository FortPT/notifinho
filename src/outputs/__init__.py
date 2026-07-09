"""
Notifinho

Output plugins.
"""

from .base import BaseOutput
from .discord import DiscordOutput

__all__ = [
    "BaseOutput",
    "DiscordOutput",
]
