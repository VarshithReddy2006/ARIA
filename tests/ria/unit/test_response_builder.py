"""Unit tests for ResponseBuilderService (Phase 8)."""

from __future__ import annotations


from ria.application.response_builder import ResponseBuilderService
from ria.domain.models.reasoning_result import ValidationResult


def test_response_builder_service() -> None:
    svc = ResponseBuilderService()
    val = ValidationResult(is_valid=True)

    res = svc.build_response("Grounded answer text", (), (), val)

    assert res.answer == "Grounded answer text"
    assert res.validation.is_valid
    assert res.quality.groundedness_score == 1.0
