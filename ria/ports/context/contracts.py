"""Canonical ports for the AI Context & Retrieval Engine.

These contracts back the public ``ria.ports.context`` package API.  They live
inside the package because Python resolves the package directory before the
legacy sibling module named ``ria.ports.context``.
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


@runtime_checkable
class IntentClassifierPort(Protocol):
    """Classify user requests deterministically."""

    def classify_intent(self, query_text: str) -> IntentClassification: ...


@runtime_checkable
class ContextPlannerPort(Protocol):
    """Convert classified intent into a context plan."""

    def plan_context(
        self, request: ContextRequest, intent: IntentClassification
    ) -> ContextPlan: ...


@runtime_checkable
class RepositoryRetrieverPort(Protocol):
    """Retrieve repository evidence candidates."""

    def retrieve(self, twin: RepositoryTwin, plan: ContextPlan) -> RetrievalResult: ...


@runtime_checkable
class RankingEnginePort(Protocol):
    """Rank retrieved evidence candidates."""

    def rank(
        self, candidates: Tuple[ContextCandidate, ...], plan: ContextPlan
    ) -> RankingResult: ...


@runtime_checkable
class CompressionEnginePort(Protocol):
    """Compress context while preserving structural semantics."""

    def compress(
        self, candidates: Tuple[ContextCandidate, ...], budget: TokenBudget
    ) -> CompressionResult: ...


@runtime_checkable
class CitationBuilderPort(Protocol):
    """Generate structured citations."""

    def build_citations(
        self, evidence_items: Tuple[ContextEvidence, ...]
    ) -> Tuple[ContextCitation, ...]: ...


@runtime_checkable
class PromptBuilderPort(Protocol):
    """Assemble complete prompt-context packages."""

    def build_prompt(
        self,
        request: ContextRequest,
        evidence_items: Tuple[ContextEvidence, ...],
        citations: Tuple[ContextCitation, ...],
    ) -> PromptContext: ...


@runtime_checkable
class TokenBudgetPort(Protocol):
    """Allocate and enforce token budgets."""

    def enforce_budget(
        self, sections: Tuple[PromptContext, ...], budget: TokenBudget
    ) -> PromptContext: ...


@runtime_checkable
class ContextCacheStore(Protocol):
    """Persist AI context cache entries."""

    def get(self, key: ContextCacheKey) -> Optional[PromptContext]: ...

    def put(self, key: ContextCacheKey, prompt: PromptContext) -> None: ...

    def invalidate_by_commit(self, commit_sha: CommitSha) -> int: ...


@runtime_checkable
class ContextRegistryPort(Protocol):
    """Track context-engine version and supported intents."""

    def engine_version(self) -> ComponentVersion: ...

    def supported_intents(self) -> FrozenSet[str]: ...
