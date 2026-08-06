"""Shared Context Port Definition."""

from typing import Protocol, Any


class SharedContextPort(Protocol):
    """Port interface for shared context management."""

    def get_context(self, session_id: str) -> Any: ...
