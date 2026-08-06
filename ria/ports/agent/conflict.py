"""Conflict Resolution Port Definition."""

from typing import Protocol, Any


class ConflictResolutionPort(Protocol):
    """Port interface for conflict resolution."""

    def resolve(self, conflicts: Any) -> Any: ...
