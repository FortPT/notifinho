"""Notifinho output plugins with lazy compatibility exports."""

__all__ = [
    "BaseOutput",
    "DiscordOutput",
    "TeamsOutput",
]


def __getattr__(name):
    if name == "BaseOutput":
        from .base import BaseOutput

        return BaseOutput
    if name == "DiscordOutput":
        from .discord import DiscordOutput

        return DiscordOutput
    if name == "TeamsOutput":
        from .teams import TeamsOutput

        return TeamsOutput
    raise AttributeError(name)
