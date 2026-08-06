"""Reasoning Engine facade application services (Phases 11 & 13).

Provides unified application interfaces: ReasoningEngineService, PromptExecutionService,
EvidenceValidationService, StreamingService, ResponseService, with observability timing metrics.
"""

from __future__ import annotations

import hashlib
import time
from typing import Iterator, Optional

from ria.application.citation_attachment import CitationAttachmentService
from ria.application.evidence_validator import EvidenceValidatorService
from ria.application.prompt_executor import PromptExecutorService
from ria.application.reasoning_pipeline import ReasoningPipelineService
from ria.application.response_builder import ResponseBuilderService
from ria.application.streaming_engine import StreamingEngineService
from ria.domain.errors import ConfigurationError
from ria.domain.models.prompt_context import PromptContext
from ria.domain.models.reasoning_model import (
    ModelRequest,
    ProviderConfiguration,
    StreamingChunk,
)
from ria.domain.models.reasoning_request import ReasoningRequest
from ria.domain.models.reasoning_result import (
    ReasoningCacheKey,
    ReasoningFingerprint,
    ReasoningResult,
    ValidationResult,
)
from ria.observability.metrics import NullMetricsSink
from ria.ports.metrics import MetricsSink
from ria.ports.reasoning import (
    ModelProviderPort,
    ReasoningCacheStore,
    ReasoningEnginePort,
)

__all__ = [
    "ReasoningEngineService",
    "PromptExecutionService",
    "EvidenceValidationService",
    "StreamingService",
    "ResponseService",
]


class PromptExecutionService:
    """Service wrapping prompt rendering and execution."""

    def __init__(self, executor: PromptExecutorService) -> None:
        self._executor = executor

    def create_request(self, prompt_context: PromptContext) -> ModelRequest:
        return self._executor.create_model_request(prompt_context)


class EvidenceValidationService:
    """Service wrapping evidence validation."""

    def __init__(self, validator: EvidenceValidatorService) -> None:
        self._validator = validator

    def validate(
        self, raw_answer: str, prompt_context: PromptContext
    ) -> ValidationResult:
        return self._validator.validate_evidence(raw_answer, prompt_context)


class StreamingService:
    """Service wrapping token streaming."""

    def __init__(self, engine: StreamingEngineService) -> None:
        self._engine = engine

    def stream(
        self, request: ModelRequest, config: ProviderConfiguration
    ) -> Iterator[StreamingChunk]:
        return self._engine.stream_response(request, config)


class ResponseService:
    """Service wrapping response building."""

    def __init__(
        self,
        citation_attachment: CitationAttachmentService,
        response_builder: ResponseBuilderService,
    ) -> None:
        self._citation_attachment = citation_attachment
        self._response_builder = response_builder

    def build(
        self,
        raw_answer: str,
        prompt_context: PromptContext,
        validation: ValidationResult,
    ) -> ReasoningResult:
        citations = self._citation_attachment.attach_citations(
            raw_answer, prompt_context.citations
        )
        return self._response_builder.build_response(
            raw_answer, (), citations, validation
        )


class ReasoningEngineService(ReasoningEnginePort):
    """Facade application service orchestrating end-to-end grounded AI Reasoning with observability."""

    def __init__(
        self,
        provider: Optional[ModelProviderPort] = None,
        cache_store: Optional[ReasoningCacheStore] = None,
        metrics_sink: Optional[MetricsSink] = None,
    ) -> None:
        self._provider = provider
        self._cache_store = cache_store
        self._metrics_sink = metrics_sink or NullMetricsSink()

        self._prompt_executor = PromptExecutorService()
        self._pipeline = ReasoningPipelineService(prompt_executor=self._prompt_executor)
        self._validator = EvidenceValidatorService()
        self._citation_attachment = CitationAttachmentService()
        self._response_builder = ResponseBuilderService()

    def execute_reasoning(
        self,
        request: ReasoningRequest,
    ) -> ReasoningResult:
        """Execute a ReasoningRequest over PromptContext with validation and caching."""
        t0 = time.perf_counter()

        prompt_str = "".join(s.content for s in request.prompt_context.sections)
        prompt_digest = hashlib.sha256(prompt_str.encode("utf-8")).hexdigest()

        fp = ReasoningFingerprint(
            prompt_digest=prompt_digest,
            provider_name=request.provider_config.provider_name,
            model_name=request.provider_config.model_name,
        )
        key = ReasoningCacheKey(fingerprint=fp)

        if self._cache_store is not None:
            cached = self._cache_store.get(key)
            if cached is not None:
                self._metrics_sink.increment("ria.reasoning.cache_hits")
                return cached

        self._metrics_sink.increment("ria.reasoning.cache_misses")

        if self._provider is None:
            raise ConfigurationError(
                "No ModelProviderPort configured for ReasoningEngineService"
            )

        # 2. Execute Reasoning Pipeline
        t_model = time.perf_counter()
        pipeline_res = self._pipeline.run_pipeline(
            request.prompt_context, self._provider, request.provider_config
        )
        self._metrics_sink.observe(
            "ria.reasoning.model_latency_seconds", time.perf_counter() - t_model
        )

        # 3. Validate Evidence
        t_val = time.perf_counter()
        val_res = self._validator.validate_evidence(
            pipeline_res.answer, request.prompt_context
        )
        self._metrics_sink.observe(
            "ria.reasoning.validation_time_seconds", time.perf_counter() - t_val
        )

        # 4. Attach Citations
        citations = self._citation_attachment.attach_citations(
            pipeline_res.answer, request.prompt_context.citations
        )

        # 5. Build Final Response
        final_res = self._response_builder.build_response(
            raw_answer=pipeline_res.answer,
            evidence=(),
            citations=citations,
            validation=val_res,
        )

        total_elapsed = time.perf_counter() - t0
        self._metrics_sink.observe("ria.reasoning.total_time_seconds", total_elapsed)

        if self._cache_store is not None:
            self._cache_store.put(key, final_res)

        return final_res
