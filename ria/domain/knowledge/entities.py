"""Entities and Containers for C8 Knowledge Layer."""

from dataclasses import dataclass, field
from typing import Optional, Tuple

from ria.domain.common.base import ValueObject
from ria.domain.knowledge.value_objects import (
    ConversationId,
    ConversationTurn,
    GroundingScore,
    KnowledgeStatistics,
    ValidationResult,
)


@dataclass(frozen=True, slots=True)
class CitationGroup(ValueObject):
    """Immutable group of verified symbol and file citations."""

    symbol_citations: Tuple[str, ...] = field(default_factory=tuple)
    file_citations: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ProviderResponse(ValueObject):
    """Immutable raw response returned from LLMProviderPort."""

    raw_text: str
    model: str
    total_tokens: int


@dataclass(frozen=True, slots=True)
class ValidationReport(ValueObject):
    """Immutable report validating grounding against ContextPackage."""

    grounding_score: GroundingScore
    result: ValidationResult


@dataclass(frozen=True, slots=True)
class GroundedAnswer(ValueObject):
    """Immutable answer container with validated citations."""

    answer_text: str
    citations: CitationGroup
    validation: ValidationReport


@dataclass(frozen=True, slots=True)
class ConversationContext(ValueObject):
    """Immutable conversation context history."""

    conversation_id: ConversationId
    turns: Tuple[ConversationTurn, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class KnowledgeSession(ValueObject):
    """Immutable session tracking active conversation state for a repository version."""

    session_id: str
    repo_id_str: str
    commit_sha: str


@dataclass(frozen=True, slots=True)
class KnowledgeResponse(ValueObject):
    """Immutable aggregate response entity returned by KnowledgeOrchestrator."""

    request_id: str
    answer: GroundedAnswer
    formatted_content: str
    statistics: KnowledgeStatistics
    is_success: bool = True
    error_message: Optional[str] = None
