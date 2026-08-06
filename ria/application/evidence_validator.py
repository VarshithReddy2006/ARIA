"""Evidence Validator application service.

Validates generated answers against PromptContext evidence and context citations,
flagging unsupported claims to produce a ValidationResult.
Implements :class:`~ria.ports.reasoning.EvidenceValidatorPort`.
"""

from __future__ import annotations

from typing import List

from ria.domain.models.prompt_context import PromptContext
from ria.domain.models.reasoning_result import ValidationResult
from ria.ports.reasoning import EvidenceValidatorPort

__all__ = ["EvidenceValidatorService"]


class EvidenceValidatorService(EvidenceValidatorPort):
    """Service for validating groundedness of AI reasoning responses."""

    def validate_evidence(
        self,
        raw_answer: str,
        prompt_context: PromptContext,
    ) -> ValidationResult:
        """Validate answer against prompt evidence."""
        evidence_corpus = " ".join(s.content.lower() for s in prompt_context.sections)

        sentences = [s.strip() for s in raw_answer.split(".") if s.strip()]
        validated: List[str] = []
        unsupported: List[str] = []

        for sent in sentences:
            words = [w.lower() for w in sent.split() if len(w) > 4]
            if not words:
                validated.append(sent)
                continue

            matches = sum(1 for w in words if w in evidence_corpus)
            match_ratio = matches / len(words)

            if match_ratio >= 0.2:
                validated.append(sent)
            else:
                unsupported.append(sent)

        is_valid = len(unsupported) == 0

        return ValidationResult(
            is_valid=is_valid,
            unsupported_claims=tuple(unsupported),
            validated_claims=tuple(validated),
        )
