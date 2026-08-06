"""Session Memory Port Protocol."""

from typing import Protocol, runtime_checkable

from ria.domain.knowledge.entities import KnowledgeSession


@runtime_checkable
class MemoryPort(Protocol):
    """Protocol for session-scoped memory management."""

    def is_session_valid(self, session: KnowledgeSession, current_commit: str) -> bool:
        """Check if session is valid for current commit."""
        ...
