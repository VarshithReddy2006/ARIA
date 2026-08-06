"""Response Builder application service.

Builds final grounded ReasoningResult containers including Answer, Reasoning Metadata, Evidence Summary,
Structured Citations, and Validation Status.
Implements :class:`~ria.ports.reasoning.ResponseBuilderPort`.
"""

from __future__ import annotations

from typing import Tuple

from ria.domain.models.reasoning_result import (
    ReasoningCitation,
    ReasoningEvidence,
    ReasoningMetadata,
    ReasoningResult,
    ReasoningStatistics,
    ResponseQuality,
    ValidationResult,
)
from ria.ports.reasoning import ResponseBuilderPort

__all__ = ["ResponseBuilderService"]


class ResponseBuilderService(ResponseBuilderPort):
    """Service for constructing final grounded ReasoningResults."""

    def build_response(
        self,
        raw_answer: str,
        evidence: Tuple[ReasoningEvidence, ...],
        citations: Tuple[ReasoningCitation, ...],
        validation: ValidationResult,
    ) -> ReasoningResult:
        """Construct final ReasoningResult."""
        groundedness = 1.0 if validation.is_valid else 0.5
        quality = ResponseQuality(
            groundedness_score=groundedness, citation_accuracy=1.0
        )
        stats = ReasoningStatistics(latency_seconds=0.1)
        meta = ReasoningMetadata(
            reasoning_id="rsn_built", provider_name="local", model_name="mock"
        )

        return ReasoningResult(
            answer=raw_answer,
            evidence=evidence,
            citations=citations,
            validation=validation,
            quality=quality,
            statistics=stats,
            metadata=meta,
        )
