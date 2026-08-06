"""Data Transfer Objects for Knowledge Subsystem."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, slots=True)
class AnswerQuestionDTO:
    """DTO requesting grounded answer to a user question."""

    repo_id: str
    question: str
    conversation_id: Optional[str] = None
    provider_name: str = "mock"


@dataclass(frozen=True, slots=True)
class KnowledgeResultDTO:
    """DTO summarizing knowledge answer response."""

    request_id: str
    conversation_id: str
    answer_text: str
    is_grounded: bool
    grounding_score: float
    total_tokens: int
    elapsed_ms: float
    is_success: bool
    error_message: Optional[str] = None
