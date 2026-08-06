"""Value Objects for C8 Knowledge Layer."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Tuple

from ria.domain.common.base import ValueObject
from ria.domain.knowledge.exceptions import InvalidKnowledgeRequestError


class IntentType(Enum):
    """Supported intent classification categories."""

    DEFINITION = "DEFINITION"
    ARCHITECTURE = "ARCHITECTURE"
    CODE_FLOW = "CODE_FLOW"
    DEPENDENCY_ANALYSIS = "DEPENDENCY_ANALYSIS"
    CALL_GRAPH = "CALL_GRAPH"
    IMPLEMENTATION_DETAILS = "IMPLEMENTATION_DETAILS"
    BUG_INVESTIGATION = "BUG_INVESTIGATION"
    REFACTORING = "REFACTORING"
    DOCUMENTATION = "DOCUMENTATION"
    COMPARISON = "COMPARISON"
    IMPACT_ANALYSIS = "IMPACT_ANALYSIS"


@dataclass(frozen=True, slots=True)
class ConversationId(ValueObject):
    """Immutable unique identifier for a conversation session."""

    value: str

    def _validate_invariants(self) -> None:
        if not self.value or not self.value.strip():
            raise InvalidKnowledgeRequestError("ConversationId value cannot be empty.")


@dataclass(frozen=True, slots=True)
class ConversationTurn(ValueObject):
    """Immutable single turn in a conversation."""

    user_message: str
    assistant_response: str


@dataclass(frozen=True, slots=True)
class ReasoningPolicy(ValueObject):
    """Immutable parameters controlling LLM reasoning execution."""

    temperature: float = 0.1
    max_tokens: int = 1500


@dataclass(frozen=True, slots=True)
class ProviderConfiguration(ValueObject):
    """Immutable configuration descriptor for LLM provider."""

    provider_name: str = "mock"
    model_name: str = "mock-model"
    api_key: str = "sk-mock"


@dataclass(frozen=True, slots=True)
class PromptPackage(ValueObject):
    """Immutable rendered prompt package passed to LLM provider."""

    system_prompt: str
    user_prompt: str


@dataclass(frozen=True, slots=True)
class GroundingScore(ValueObject):
    """Immutable grounding confidence score."""

    score_value: float
    is_grounded: bool


@dataclass(frozen=True, slots=True)
class ValidationResult(ValueObject):
    """Immutable validation result for grounded citations."""

    is_valid: bool
    invalid_citations: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class KnowledgeStatistics(ValueObject):
    """Immutable execution statistics for Knowledge Layer operations."""

    intent_ms: float
    prompt_ms: float
    provider_ms: float
    validation_ms: float
    format_ms: float


@dataclass(frozen=True, slots=True)
class KnowledgeRequest(ValueObject):
    """Immutable request entity for Knowledge Layer."""

    conversation_id: ConversationId
    question: str
    provider_config: ProviderConfiguration = field(
        default_factory=ProviderConfiguration
    )

    def _validate_invariants(self) -> None:
        if not self.question or not self.question.strip():
            raise InvalidKnowledgeRequestError(
                "KnowledgeRequest question cannot be empty."
            )
