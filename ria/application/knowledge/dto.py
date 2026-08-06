"""Data Transfer Objects for Knowledge Application Layer."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, slots=True)
class AnswerQuestionCommandDTO:
    """DTO requesting grounded answer to a user question."""

    repo_id: str
    question: str
    conversation_id: Optional[str] = None
    provider_name: str = "mock"


@dataclass(frozen=True, slots=True)
class ValidateResponseCommandDTO:
    """DTO requesting response validation."""

    raw_response: str
    context_package_id: str


@dataclass(frozen=True, slots=True)
class ManageConversationCommandDTO:
    """DTO managing conversation session."""

    conversation_id: str
    action: str = "get"  # "get" or "clear"
