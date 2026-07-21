"""Central ownership policy for user-scoped platform resources."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Actor:
    user_id: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


class OwnershipPolicy:
    """Apply one policy consistently to destinations, routes, and secrets."""

    @staticmethod
    def can_read(actor: Actor | None, owner_user_id: str, shared: bool = False) -> bool:
        if actor is None:
            return False
        return actor.is_admin or actor.user_id == owner_user_id or bool(shared)

    @staticmethod
    def can_write(actor: Actor | None, owner_user_id: str) -> bool:
        if actor is None:
            return False
        return actor.is_admin or actor.user_id == owner_user_id

    @classmethod
    def require_read(
        cls,
        actor: Actor | None,
        owner_user_id: str,
        shared: bool = False,
    ) -> None:
        if not cls.can_read(actor, owner_user_id, shared):
            raise PermissionError("resource is not available to this user")

    @classmethod
    def require_write(cls, actor: Actor | None, owner_user_id: str) -> None:
        if not cls.can_write(actor, owner_user_id):
            raise PermissionError("resource cannot be changed by this user")
