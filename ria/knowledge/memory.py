"""Session Memory implementing MemoryPort."""

from ria.domain.knowledge.entities import KnowledgeSession
from ria.ports.knowledge.memory import MemoryPort


class SessionMemory(MemoryPort):
    """Session memory verifying that sessions remain valid for current repository commit."""

    def is_session_valid(self, session: KnowledgeSession, current_commit: str) -> bool:
        return session.commit_sha == current_commit
