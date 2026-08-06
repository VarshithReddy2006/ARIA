"""Unit tests for CompressionEngineService (Phase 7)."""

from __future__ import annotations


from ria.application.context_compression import CompressionEngineService
from ria.domain.models.context_evidence import ContextCandidate
from ria.domain.models.token_budget import TokenBudget


def test_compression_engine_service() -> None:
    svc = CompressionEngineService()

    c1 = ContextCandidate(
        id="c1",
        kind="symbol",
        content="def main(): pass",
        location_path="main.py",
        raw_score=0.9,
    )
    c2 = ContextCandidate(
        id="c2",
        kind="symbol",
        content="def main(): pass",
        location_path="main.py",
        raw_score=0.9,
    )

    budget = TokenBudget(evidence_reserved=1000)
    res = svc.compress((c1, c2), budget)

    # c2 deduplicated because content is identical
    assert len(res.compressed_items) == 1
    assert res.compressed_items[0].id == "c1"
