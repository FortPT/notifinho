"""HTTP response value shared by the API service and native HTTP input."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class APIResponse:
    status: int
    payload: object = None
    headers: tuple[tuple[str, str], ...] = ()

    def legacy(self) -> tuple[int, object]:
        """Return the historical two-item APIService result."""

        return self.status, self.payload
