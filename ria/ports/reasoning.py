"""Port protocols for Milestone 9 — AI Reasoning Engine.

Defines runtime checkable protocols for reasoning execution, model provider abstraction,
prompt execution, evidence validation, citation attachment, streaming, caching, and registry.
"""

from __future__ import annotations

from typing import FrozenSet, Iterator, Optional, Protocol, Tuple, runtime_checkable

from ria.domain.identity import CommitSha
from ria.domain.models.parser_identity import ComponentVersion
from ria.domain.models.prompt_context import ContextCitation, PromptContext
from ria.domain.models.reasoning_model import (
    ModelRequest,
    ModelResponse,
    PromptExecution,
    PromptTemplate,
    ProviderConfiguration,
    StreamingChunk,
)
from ria.domain.models.reasoning_request import ReasoningRequest
from ria.domain.models.reasoning_result import (
    ReasoningCacheKey,
    ReasoningCitation,
    ReasoningEvidence,
    ReasoningResult,
    ValidationResult,
)

__all__ = [
    "ReasoningEnginePort",
    "ModelProviderPort",
    "PromptExecutorPort",
    "EvidenceValidatorPort",
    "CitationAttachmentPort",
    "StreamingPort",
    "ReasoningCacheStore",
    "ReasoningRegistryPort",
    "ResponseBuilderPort",
    "PromptTemplatePort",
]


@runtime_checkable
class ReasoningEnginePort(Protocol):
    """Port for executing grounded AI Reasoning requests."""

    def execute_reasoning(
        self,
        request: ReasoningRequest,
    ) -> ReasoningResult:
        """Execute a ReasoningRequest on a PromptContext."""
        ...


@runtime_checkable
class ModelProviderPort(Protocol):
    """Port for provider-independent LLM execution."""

    def execute_model(
        self,
        request: ModelRequest,
        config: ProviderConfiguration,
    ) -> ModelResponse:
        """Execute ModelRequest on provider target."""
        ...

    def provider_name(self) -> str:
        """Return provider name (e.g. 'openai', 'anthropic', 'google', 'local')."""
        ...


@runtime_checkable
class PromptExecutorPort(Protocol):
    """Port for executing prompt rendering and formatting."""

    def execute_prompt(
        self,
        prompt_context: PromptContext,
        template: PromptTemplate,
    ) -> PromptExecution:
        """Render and format PromptContext using template."""
        ...


@runtime_checkable
class EvidenceValidatorPort(Protocol):
    """Port for validating generated answers against prompt evidence."""

    def validate_evidence(
        self,
        raw_answer: str,
        prompt_context: PromptContext,
    ) -> ValidationResult:
        """Validate answer against prompt evidence."""
        ...


@runtime_checkable
class CitationAttachmentPort(Protocol):
    """Port for attaching structured citations to grounded claims."""

    def attach_citations(
        self,
        raw_answer: str,
        citations: Tuple[ContextCitation, ...],
    ) -> Tuple[ReasoningCitation, ...]:
        """Attach ReasoningCitations to answer."""
        ...


@runtime_checkable
class StreamingPort(Protocol):
    """Port for streaming model token responses."""

    def stream_response(
        self,
        request: ModelRequest,
        config: ProviderConfiguration,
    ) -> Iterator[StreamingChunk]:
        """Stream response chunks for request."""
        ...


@runtime_checkable
class ReasoningCacheStore(Protocol):
    """Port for durable AI Reasoning caching."""

    def get(self, key: ReasoningCacheKey) -> Optional[ReasoningResult]:
        """Retrieve cached ReasoningResult."""
        ...

    def put(self, key: ReasoningCacheKey, result: ReasoningResult) -> None:
        """Cache ReasoningResult."""
        ...

    def invalidate_by_commit(self, commit_sha: CommitSha) -> int:
        """Invalidate reasoning cache entries for a commit."""
        ...


@runtime_checkable
class ReasoningRegistryPort(Protocol):
    """Port for tracking reasoning engine version and supported providers."""

    def engine_version(self) -> ComponentVersion:
        """Return ComponentVersion of the reasoning engine."""
        ...

    def supported_providers(self) -> FrozenSet[str]:
        """Return set of supported provider names."""
        ...


@runtime_checkable
class ResponseBuilderPort(Protocol):
    """Port for constructing final grounded ReasoningResults."""

    def build_response(
        self,
        raw_answer: str,
        evidence: Tuple[ReasoningEvidence, ...],
        citations: Tuple[ReasoningCitation, ...],
        validation: ValidationResult,
    ) -> ReasoningResult:
        """Construct ReasoningResult."""
        ...


@runtime_checkable
class PromptTemplatePort(Protocol):
    """Port for loading and rendering prompt templates."""

    def get_template(self, name: str) -> PromptTemplate:
        """Get PromptTemplate by name."""
        ...
