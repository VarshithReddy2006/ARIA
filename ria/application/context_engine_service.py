"""Context Engine facade application services (Phases 12 & 13).

Provides unified application interfaces: ContextEngineService, RetrievalService, RankingService,
CompressionService, PromptAssemblyService, with observability timing metrics.
"""

from __future__ import annotations

import time
from typing import Optional, Tuple

from ria.application.citation_builder import CitationBuilderService
from ria.application.context_compression import CompressionEngineService
from ria.application.context_planner import ContextPlannerService
from ria.application.intent_classifier import IntentClassifierService
from ria.application.prompt_context_builder import PromptContextBuilderService
from ria.application.ranking_engine import RankingEngineService
from ria.application.repository_retriever import RepositoryRetrieverService
from ria.application.token_budget_manager import TokenBudgetManagerService
from ria.domain.models.context_evidence import ContextCandidate, ContextEvidence
from ria.domain.models.context_plan import ContextPlan
from ria.domain.models.context_request import ContextRequest
from ria.domain.models.context_result import (
    CompressionResult,
    ContextCacheKey,
    ContextFingerprint,
    RankingResult,
    RetrievalResult,
)
from ria.domain.models.prompt_context import PromptContext
from ria.domain.models.repository_twin import RepositoryTwin
from ria.observability.metrics import NullMetricsSink
from ria.ports.context import ContextCacheStore
from ria.ports.metrics import MetricsSink

__all__ = [
    "ContextEngineService",
    "RetrievalService",
    "RankingService",
    "CompressionService",
    "PromptAssemblyService",
]


class RetrievalService:
    """Service wrapping candidate retrieval."""

    def __init__(self, retriever: RepositoryRetrieverService) -> None:
        self._retriever = retriever

    def retrieve(self, twin: RepositoryTwin, plan: ContextPlan) -> RetrievalResult:
        return self._retriever.retrieve(twin, plan)


class RankingService:
    """Service wrapping candidate ranking."""

    def __init__(self, ranker: RankingEngineService) -> None:
        self._ranker = ranker

    def rank(
        self, candidates: Tuple[ContextCandidate, ...], plan: ContextPlan
    ) -> RankingResult:
        return self._ranker.rank(candidates, plan)


class CompressionService:
    """Service wrapping context compression."""

    def __init__(self, compressor: CompressionEngineService) -> None:
        self._compressor = compressor

    def compress(
        self, candidates: Tuple[ContextCandidate, ...], request: ContextRequest
    ) -> CompressionResult:
        return self._compressor.compress(candidates, request.token_budget)


class PromptAssemblyService:
    """Service wrapping prompt context assembly and citation generation."""

    def __init__(
        self,
        citation_builder: CitationBuilderService,
        prompt_builder: PromptContextBuilderService,
        budget_manager: TokenBudgetManagerService,
    ) -> None:
        self._citations = citation_builder
        self._prompt_builder = prompt_builder
        self._budget = budget_manager

    def assemble(
        self,
        request: ContextRequest,
        evidence_items: Tuple[ContextEvidence, ...],
    ) -> PromptContext:
        citations = self._citations.build_citations(evidence_items)
        prompt = self._prompt_builder.build_prompt(request, evidence_items, citations)
        return self._budget.enforce_budget((prompt,), request.token_budget)


class ContextEngineService:
    """Facade application service orchestrating end-to-end AI context retrieval with observability."""

    def __init__(
        self,
        cache_store: Optional[ContextCacheStore] = None,
        metrics_sink: Optional[MetricsSink] = None,
    ) -> None:
        self._cache_store = cache_store
        self._metrics_sink = metrics_sink or NullMetricsSink()

        self._classifier = IntentClassifierService()
        self._planner = ContextPlannerService()
        self._retriever = RepositoryRetrieverService()
        self._ranker = RankingEngineService()
        self._compressor = CompressionEngineService()
        self._citation_builder = CitationBuilderService()
        self._prompt_builder = PromptContextBuilderService()
        self._budget_manager = TokenBudgetManagerService()

    def build_context(
        self,
        twin: RepositoryTwin,
        request: ContextRequest,
    ) -> PromptContext:
        """Build a complete PromptContext package for a ContextRequest on a RepositoryTwin."""
        t0 = time.perf_counter()

        # Cache check
        fp = ContextFingerprint(
            query_text=request.query_text,
            intent_type="general",
            max_tokens=request.token_budget.max_tokens,
        )
        key = ContextCacheKey(
            repository_id=request.repository_id,
            commit_sha=request.commit_sha,
            fingerprint=fp,
        )

        if self._cache_store is not None:
            cached = self._cache_store.get(key)
            if cached is not None:
                self._metrics_sink.increment("ria.context.cache_hits")
                return cached

        self._metrics_sink.increment("ria.context.cache_misses")

        # 1. Classify Intent
        intent = self._classifier.classify_intent(request.query_text)

        # 2. Plan Context
        plan = self._planner.plan_context(request, intent)

        # 3. Retrieve Evidence
        t_ret = time.perf_counter()
        retrieval_res = self._retriever.retrieve(twin, plan)
        self._metrics_sink.observe(
            "ria.context.retrieval_time_seconds", time.perf_counter() - t_ret
        )

        # 4. Rank Candidates
        t_rank = time.perf_counter()
        ranking_res = self._ranker.rank(retrieval_res.candidates, plan)
        self._metrics_sink.observe(
            "ria.context.ranking_time_seconds", time.perf_counter() - t_rank
        )

        # 5. Compress Context
        t_comp = time.perf_counter()
        comp_res = self._compressor.compress(
            ranking_res.ranked_candidates, request.token_budget
        )
        self._metrics_sink.observe(
            "ria.context.compression_time_seconds", time.perf_counter() - t_comp
        )

        # 6. Build Citations & Prompt
        t_asm = time.perf_counter()
        citations = self._citation_builder.build_citations(comp_res.compressed_items)
        prompt = self._prompt_builder.build_prompt(
            request, comp_res.compressed_items, citations
        )
        final_prompt = self._budget_manager.enforce_budget(
            (prompt,), request.token_budget
        )
        self._metrics_sink.observe(
            "ria.context.assembly_time_seconds", time.perf_counter() - t_asm
        )

        total_elapsed = time.perf_counter() - t0
        self._metrics_sink.observe("ria.context.total_time_seconds", total_elapsed)

        if self._cache_store is not None:
            self._cache_store.put(key, final_prompt)

        return final_prompt
