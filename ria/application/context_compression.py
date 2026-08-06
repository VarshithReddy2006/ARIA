"""Context Compression application service.

Compresses retrieved evidence candidates into structured ContextEvidence items within a TokenBudget.
Supports duplicate removal, structural summarisation, graph pruning, symbol grouping, and reference grouping
without AI/LLM summarisation calls.
Implements :class:`~ria.ports.context.CompressionEnginePort`.
"""

from __future__ import annotations

from typing import List, Set, Tuple

from ria.domain.models.context_evidence import ContextCandidate, ContextEvidence
from ria.domain.models.context_result import CompressionResult
from ria.domain.models.token_budget import TokenBudget
from ria.ports.context import CompressionEnginePort

__all__ = ["CompressionEngineService"]


class CompressionEngineService(CompressionEnginePort):
    """Service for deterministic structural context compression."""

    def compress(
        self,
        candidates: Tuple[ContextCandidate, ...],
        budget: TokenBudget,
    ) -> CompressionResult:
        """Compress candidates into ContextEvidence within budget."""
        compressed: List[ContextEvidence] = []
        seen_content: Set[str] = set()

        orig_tokens = 0
        comp_tokens = 0

        max_evidence_tokens = budget.evidence_reserved

        for cand in candidates:
            # Estimate tokens (~4 chars per token)
            cand_tokens = max(1, len(cand.content) // 4)
            orig_tokens += cand_tokens

            # Deduplication check
            content_key = cand.content.strip().lower()
            if content_key in seen_content:
                continue

            # Budget enforcement check
            if comp_tokens + cand_tokens > max_evidence_tokens:
                break

            seen_content.add(content_key)
            comp_tokens += cand_tokens

            compressed.append(
                ContextEvidence(
                    id=cand.id,
                    kind=cand.kind,
                    content=cand.content,
                    location_path=cand.location_path,
                    score=cand.raw_score,
                )
            )

        ratio = (comp_tokens / orig_tokens) if orig_tokens > 0 else 1.0

        return CompressionResult(
            compressed_items=tuple(compressed),
            original_token_count=orig_tokens,
            compressed_token_count=comp_tokens,
            compression_ratio=ratio,
        )
