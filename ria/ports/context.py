"""Port protocols for Milestone 8 — AI Context & Retrieval Engine.

Defines runtime checkable protocols for intent classification, context planning, repository retrieval,
ranking, compression, citation building, prompt building, token budgeting, context caching, and context registry.
"""

from __future__ import annotations

from typing import FrozenSet, Optional, Protocol, Tuple, runtime_checkable

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

__all__ = [
    "IntentClassifierPort",
    "ContextPlannerPort",
    "RepositoryRetrieverPort",
    "RankingEnginePort",
    "CompressionEnginePort",
    "CitationBuilderPort",
    "PromptBuilderPort",
    "TokenBudgetPort",
    "ContextCacheStore",
    "ContextRegistryPort",
]


@runtime_checkable
class IntentClassifierPort(Protocol):
    """Port for deterministic intent classification of user requests."""

    def classify_intent(self, query_text: str) -> IntentClassification:
        """Classify user query text into an IntentClassification."""
        ...


@runtime_checkable
class ContextPlannerPort(Protocol):
    """Port for converting classified intent into a ContextPlan."""

    def plan_context(
        self,
        request: ContextRequest,
        intent: IntentClassification,
    ) -> ContextPlan:
        """Construct a ContextPlan for retrieval."""
        ...


@runtime_checkable
class RepositoryRetrieverPort(Protocol):
    """Port for retrieving repository evidence candidates."""

    def retrieve(
        self,
        twin: RepositoryTwin,
        plan: ContextPlan,
    ) -> RetrievalResult:
        """Retrieve evidence candidates according to plan."""
        ...


@runtime_checkable
class RankingEnginePort(Protocol):
    """Port for ranking retrieved evidence candidates."""

    def rank(
        self,
        candidates: Tuple[ContextCandidate, ...],
        plan: ContextPlan,
    ) -> RankingResult:
        """Rank evidence candidates by relevance score."""
        ...


@runtime_checkable
class CompressionEnginePort(Protocol):
    """Port for compressing context while preserving structural semantics."""

    def compress(
        self,
        candidates: Tuple[ContextCandidate, ...],
        budget: TokenBudget,
    ) -> CompressionResult:
        """Compress context items into ContextEvidence."""
        ...


@runtime_checkable
class CitationBuilderPort(Protocol):
    """Port for generating structured citations."""

    def build_citations(
        self,
        evidence_items: Tuple[ContextEvidence, ...],
    ) -> Tuple[ContextCitation, ...]:
        """Generate ContextCitations for evidence items."""
        ...


@runtime_checkable
class PromptBuilderPort(Protocol):
    """Port for assembling complete PromptContext packages."""

    def build_prompt(
        self,
        request: ContextRequest,
        evidence_items: Tuple[ContextEvidence, ...],
        citations: Tuple[ContextCitation, ...],
    ) -> PromptContext:
        """Assemble PromptContext."""
        ...


@runtime_checkable
class TokenBudgetPort(Protocol):
    """Port for allocating and enforcing token budgets."""

    def enforce_budget(
        self,
        sections: Tuple[PromptContext, ...],
        budget: TokenBudget,
    ) -> PromptContext:
        """Enforce token limits across prompt sections."""
        ...


@runtime_checkable
class ContextCacheStore(Protocol):
    """Port for durable AI Context caching."""

    def get(self, key: ContextCacheKey) -> Optional[PromptContext]:
        """Retrieve cached PromptContext."""
        ...

    def put(self, key: ContextCacheKey, prompt: PromptContext) -> None:
        """Cache PromptContext."""
        ...

    def invalidate_by_commit(self, commit_sha: CommitSha) -> int:
        """Invalidate context cache entries for a commit."""
        ...


@runtime_checkable
class ContextRegistryPort(Protocol):
    """Port for tracking context engine version and supported intents."""

    def engine_version(self) -> ComponentVersion:
        """Return ComponentVersion of the context engine."""
        ...

    def supported_intents(self) -> FrozenSet[str]:
        """Return set of supported intent types."""
        ...
