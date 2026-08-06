"""Context request and intent classification domain models.

Defines IntentClassification, ConversationContext, RepositoryContext, and ContextRequest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.context_id import ContextId
from ria.domain.models.token_budget import TokenBudget

__all__ = [
    "IntentClassification",
    "ConversationContext",
    "RepositoryContext",
    "ContextRequest",
]


@dataclass(frozen=True)
class IntentClassification:
    """Deterministic intent classification output.

    Attributes:
        intent_type: Categorized intent (e.g. 'explain_code', 'find_bug', 'trace_dependency').
        confidence: Confidence score in [0.0, 1.0].
        keywords: Matched keywords or tokens.
    """

    intent_type: str
    confidence: float = 1.0
    keywords: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be within [0, 1], got {self.confidence}")


@dataclass(frozen=True)
class ConversationContext:
    """Chat memory context for multi-turn conversations.

    Attributes:
        messages: Previous conversation messages (role, content tuples).
    """

    messages: Tuple[Tuple[str, str], ...] = ()


@dataclass(frozen=True)
class RepositoryContext:
    """Summary context of the target repository.

    Attributes:
        repository_name: Name of the repository.
        language: Dominant programming language.
        files_count: Total files count.
        symbols_count: Total symbols count.
    """

    repository_name: str
    language: str = "unknown"
    files_count: int = 0
    symbols_count: int = 0


@dataclass(frozen=True)
class ContextRequest:
    """Complete Context Retrieval request.

    Attributes:
        context_id: Unique ContextId.
        query_text: User request text.
        repository_id: Identity of the target repository.
        commit_sha: Bound commit SHA.
        token_budget: Active TokenBudget constraints.
        conversation: Optional ConversationContext.
    """

    context_id: ContextId
    query_text: str
    repository_id: RepositoryId
    commit_sha: CommitSha
    token_budget: TokenBudget = field(default_factory=TokenBudget)
    conversation: ConversationContext = field(default_factory=ConversationContext)
