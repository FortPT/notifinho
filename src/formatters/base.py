"""
Notifinho

Base formatter interface.

All notification formatters should inherit from this class.
"""

from abc import ABC, abstractmethod

from formatters.presentation import PresentationMixin


class BaseFormatter(PresentationMixin, ABC):
    """Base class for all notification formatters."""

    @abstractmethod
    def format(self, notification):
        """
        Convert a Notification object into the
        platform-specific payload.

        Returns:
            object
        """
        pass
