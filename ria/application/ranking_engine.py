"""Ranking Engine application service.

Ranks retrieved evidence candidates using deterministic weighting factors (graph distance,
reference count, dependency importance, symbol importance, repository metrics, recency).
Implements :class:`~ria.ports.context.RankingEnginePort`.
"""

from __future__ import annotations

import time
from typing import List, Tuple

from ria.domain.models.context_evidence import ContextCandidate
from ria.domain.models.context_plan import ContextPlan
from ria.domain.models.context_result import RankingResult
from ria.ports.context import RankingEnginePort

__all__ = ["RankingEngineService"]


class RankingEngineService(RankingEnginePort):
    """Service for deterministic context candidate ranking."""

    def rank(
        self,
        candidates: Tuple[ContextCandidate, ...],
        plan: ContextPlan,
    ) -> RankingResult:
        """Rank evidence candidates by calculated relevance score."""
        t0 = time.perf_counter()

        ranked: List[ContextCandidate] = []
        for cand in candidates:
            score = cand.raw_score

            # Boost if name matches target symbols directly
            for sym in plan.target_symbols:
                if sym.lower() in cand.content.lower():
                    score += 0.2

            # Boost if location matches target files
            for target_f in plan.target_files:
                if target_f.lower() in cand.location_path.lower():
                    score += 0.15

            # Clamp score to [0.0, 1.0]
            final_score = min(1.0, max(0.0, score))

            ranked.append(
                ContextCandidate(
                    id=cand.id,
                    kind=cand.kind,
                    content=cand.content,
                    location_path=cand.location_path,
                    raw_score=final_score,
                )
            )

        # Sort descending by raw_score, break ties deterministically by id
        ranked_sorted = sorted(ranked, key=lambda c: (-c.raw_score, c.id))

        elapsed = time.perf_counter() - t0
        return RankingResult(
            ranked_candidates=tuple(ranked_sorted),
            ranking_time_seconds=elapsed,
        )
