"""Unit tests for EvidenceValidatorService (Phase 6)."""

from __future__ import annotations


from ria.application.evidence_validator import EvidenceValidatorService
from ria.domain.models.prompt_context import PromptContext, PromptSection


def test_evidence_validator_service() -> None:
    svc = EvidenceValidatorService()
    sec = PromptSection(title="Section", content="function main executes application")
    p_ctx = PromptContext(sections=(sec,))

    res1 = svc.validate_evidence("Function main executes application", p_ctx)
    assert res1.is_valid

    res2 = svc.validate_evidence("Random completely unrelated fake statement", p_ctx)
    assert not res2.is_valid
    assert len(res2.unsupported_claims) > 0
