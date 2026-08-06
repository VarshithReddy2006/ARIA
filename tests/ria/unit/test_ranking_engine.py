"""Unit tests for RankingEngineService (Phase 6)."""

from __future__ import annotations


from ria.application.ranking_engine import RankingEngineService
from ria.domain.models.context_evidence import ContextCandidate
from ria.domain.models.context_plan import ContextPlan
from ria.domain.models.context_request import IntentClassification


def test_ranking_engine_service() -> None:
    svc = RankingEngineService()
    c1 = ContextCandidate(
        id="c1",
        kind="symbol",
        content="def main(): pass",
        location_path="main.py",
        raw_score=0.5,
    )
    c2 = ContextCandidate(
        id="c2",
        kind="symbol",
        content="def aux(): pass",
        location_path="aux.py",
        raw_score=0.5,
    )

    plan = ContextPlan(
        intent=IntentClassification("explain_code"), target_symbols=("main",)
    )
    res = svc.rank((c1, c2), plan)

    assert len(res.ranked_candidates) == 2
    assert res.ranked_candidates[0].id == "c1"  # c1 boosted because 'main' in content
