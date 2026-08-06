"""Unit tests for Phase 2 context ports runtime conformance."""

from __future__ import annotations

from typing import FrozenSet, Optional, Tuple

from ria.domain.identity import CommitSha
from ria.domain.models.context_evidence import ContextCandidate, ContextEvidence
from ria.domain.models.context_plan import ContextPlan
from ria.domain.models.context_request import ContextRequest, IntentClassification
from ria.domain.models.context_result import (
    CompressionResult,
    ContextCacheKey,
    RankingResult,
    RetrievalResult,
)
from ria.domain.models.parser_identity import ComponentVersion
from ria.domain.models.prompt_context import ContextCitation, PromptContext
from ria.domain.models.repository_twin import RepositoryTwin
from ria.domain.models.token_budget import TokenBudget
from ria.ports.context import (
    CitationBuilderPort,
    CompressionEnginePort,
    ContextCacheStore,
    ContextPlannerPort,
    ContextRegistryPort,
    IntentClassifierPort,
    PromptBuilderPort,
    RankingEnginePort,
    RepositoryRetrieverPort,
    TokenBudgetPort,
)


class DummyIntentClassifier:
    def classify_intent(self, query_text: str) -> IntentClassification:
        return IntentClassification("explain_code")


class DummyContextPlanner:
    def plan_context(
        self, request: ContextRequest, intent: IntentClassification
    ) -> ContextPlan:
        return ContextPlan(intent=intent)


class DummyRepositoryRetriever:
    def retrieve(self, twin: RepositoryTwin, plan: ContextPlan) -> RetrievalResult:
        return RetrievalResult()


class DummyRankingEngine:
    def rank(
        self, candidates: Tuple[ContextCandidate, ...], plan: ContextPlan
    ) -> RankingResult:
        return RankingResult()


class DummyCompressionEngine:
    def compress(
        self, candidates: Tuple[ContextCandidate, ...], budget: TokenBudget
    ) -> CompressionResult:
        return CompressionResult()


class DummyCitationBuilder:
    def build_citations(
        self, evidence_items: Tuple[ContextEvidence, ...]
    ) -> Tuple[ContextCitation, ...]:
        return ()


class DummyPromptBuilder:
    def build_prompt(
        self,
        request: ContextRequest,
        evidence_items: Tuple[ContextEvidence, ...],
        citations: Tuple[ContextCitation, ...],
    ) -> PromptContext:
        return PromptContext()


class DummyTokenBudgetManager:
    def enforce_budget(
        self, sections: Tuple[PromptContext, ...], budget: TokenBudget
    ) -> PromptContext:
        return PromptContext()


class DummyContextCacheStore:
    def get(self, key: ContextCacheKey) -> Optional[PromptContext]:
        return None

    def put(self, key: ContextCacheKey, prompt: PromptContext) -> None:
        pass

    def invalidate_by_commit(self, commit_sha: CommitSha) -> int:
        return 0


class DummyContextRegistry:
    def engine_version(self) -> ComponentVersion:
        return ComponentVersion("dummy-context", "1.0.0")

    def supported_intents(self) -> FrozenSet[str]:
        return frozenset({"explain_code", "find_bug"})


def test_context_ports_conformance() -> None:
    assert isinstance(DummyIntentClassifier(), IntentClassifierPort)
    assert isinstance(DummyContextPlanner(), ContextPlannerPort)
    assert isinstance(DummyRepositoryRetriever(), RepositoryRetrieverPort)
    assert isinstance(DummyRankingEngine(), RankingEnginePort)
    assert isinstance(DummyCompressionEngine(), CompressionEnginePort)
    assert isinstance(DummyCitationBuilder(), CitationBuilderPort)
    assert isinstance(DummyPromptBuilder(), PromptBuilderPort)
    assert isinstance(DummyTokenBudgetManager(), TokenBudgetPort)
    assert isinstance(DummyContextCacheStore(), ContextCacheStore)
    assert isinstance(DummyContextRegistry(), ContextRegistryPort)
