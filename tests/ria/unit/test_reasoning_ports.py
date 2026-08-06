"""Unit tests for Phase 2 reasoning ports runtime conformance."""

from __future__ import annotations

from typing import FrozenSet, Iterator, Optional, Tuple

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
from ria.ports.reasoning import (
    CitationAttachmentPort,
    EvidenceValidatorPort,
    ModelProviderPort,
    PromptExecutorPort,
    PromptTemplatePort,
    ReasoningCacheStore,
    ReasoningEnginePort,
    ReasoningRegistryPort,
    ResponseBuilderPort,
    StreamingPort,
)


class DummyReasoningEngine:
    def execute_reasoning(self, request: ReasoningRequest) -> ReasoningResult:
        return ReasoningResult(answer="mock")


class DummyModelProvider:
    def execute_model(
        self, request: ModelRequest, config: ProviderConfiguration
    ) -> ModelResponse:
        return ModelResponse(raw_text="mock", model_name=config.model_name)

    def provider_name(self) -> str:
        return "dummy"


class DummyPromptExecutor:
    def execute_prompt(
        self, prompt_context: PromptContext, template: PromptTemplate
    ) -> PromptExecution:
        return PromptExecution(template_name=template.name, rendered_prompt="mock")


class DummyEvidenceValidator:
    def validate_evidence(
        self, raw_answer: str, prompt_context: PromptContext
    ) -> ValidationResult:
        return ValidationResult()


class DummyCitationAttachment:
    def attach_citations(
        self, raw_answer: str, citations: Tuple[ContextCitation, ...]
    ) -> Tuple[ReasoningCitation, ...]:
        return ()


class DummyStreamingEngine:
    def stream_response(
        self, request: ModelRequest, config: ProviderConfiguration
    ) -> Iterator[StreamingChunk]:
        yield StreamingChunk(
            session_id="s1", chunk_index=0, text_delta="mock", is_final=True
        )


class DummyReasoningCacheStore:
    def get(self, key: ReasoningCacheKey) -> Optional[ReasoningResult]:
        return None

    def put(self, key: ReasoningCacheKey, result: ReasoningResult) -> None:
        pass

    def invalidate_by_commit(self, commit_sha: CommitSha) -> int:
        return 0


class DummyReasoningRegistry:
    def engine_version(self) -> ComponentVersion:
        return ComponentVersion("dummy-reasoning", "1.0.0")

    def supported_providers(self) -> FrozenSet[str]:
        return frozenset({"openai", "anthropic", "google", "local"})


class DummyResponseBuilder:
    def build_response(
        self,
        raw_answer: str,
        evidence: Tuple[ReasoningEvidence, ...],
        citations: Tuple[ReasoningCitation, ...],
        validation: ValidationResult,
    ) -> ReasoningResult:
        return ReasoningResult(answer=raw_answer)


class DummyPromptTemplateProvider:
    def get_template(self, name: str) -> PromptTemplate:
        return PromptTemplate(name=name, template_text="mock")


def test_reasoning_ports_conformance() -> None:
    assert isinstance(DummyReasoningEngine(), ReasoningEnginePort)
    assert isinstance(DummyModelProvider(), ModelProviderPort)
    assert isinstance(DummyPromptExecutor(), PromptExecutorPort)
    assert isinstance(DummyEvidenceValidator(), EvidenceValidatorPort)
    assert isinstance(DummyCitationAttachment(), CitationAttachmentPort)
    assert isinstance(DummyStreamingEngine(), StreamingPort)
    assert isinstance(DummyReasoningCacheStore(), ReasoningCacheStore)
    assert isinstance(DummyReasoningRegistry(), ReasoningRegistryPort)
    assert isinstance(DummyResponseBuilder(), ResponseBuilderPort)
    assert isinstance(DummyPromptTemplateProvider(), PromptTemplatePort)
