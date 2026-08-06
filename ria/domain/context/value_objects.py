"""Value Objects for C7 Context Builder."""

from dataclasses import dataclass, field
from typing import Tuple

from ria.domain.common.base import ValueObject
from ria.domain.context.exceptions import InvalidContextRequestError
from ria.domain.index.value_objects import FilePath
from ria.domain.resolution.value_objects import SymbolMoniker


@dataclass(frozen=True, slots=True)
class Citation(ValueObject):
    """Immutable citation tracking precise repository origin of a context snippet."""

    repo_name: str
    commit_sha: str
    file_path: FilePath
    module_name: str
    symbol_moniker: SymbolMoniker
    start_line: int
    end_line: int


@dataclass(frozen=True, slots=True)
class TokenBudget(ValueObject):
    """Immutable token budget constraint for assembled context."""

    max_tokens: int = 4000

    def _validate_invariants(self) -> None:
        if self.max_tokens <= 0:
            raise InvalidContextRequestError("max_tokens must be greater than zero.")


@dataclass(frozen=True, slots=True)
class RankingScore(ValueObject):
    """Immutable deterministic relevance score for context ranking."""

    priority: int
    score_value: float
    category: str


@dataclass(frozen=True, slots=True)
class ExpansionRule(ValueObject):
    """Immutable configuration rules for expansion pipeline depth and relations."""

    max_depth: int = 2
    include_callers: bool = True
    include_callees: bool = True
    include_dependencies: bool = True
    include_imports: bool = True


@dataclass(frozen=True, slots=True)
class ContextScope(ValueObject):
    """Immutable scope filtering context assembly."""

    file_paths: Tuple[FilePath, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ContextOptions(ValueObject):
    """Immutable context configuration options."""

    token_budget: TokenBudget = field(default_factory=TokenBudget)
    expansion_rule: ExpansionRule = field(default_factory=ExpansionRule)
    scope: ContextScope = field(default_factory=ContextScope)


@dataclass(frozen=True, slots=True)
class ContextRequest(ValueObject):
    """Immutable domain request for building context."""

    question: str
    options: ContextOptions = field(default_factory=ContextOptions)

    def _validate_invariants(self) -> None:
        if not self.question or not self.question.strip():
            raise InvalidContextRequestError("question cannot be empty.")


@dataclass(frozen=True, slots=True)
class ContextBudget(ValueObject):
    """Immutable token budget tracking during assembly."""

    max_tokens: int
    estimated_used_tokens: int = 0


@dataclass(frozen=True, slots=True)
class ContextStatistics(ValueObject):
    """Immutable performance statistics for Context Builder execution."""

    expansion_ms: float
    ranking_ms: float
    deduplication_ms: float
    optimization_ms: float
    total_snippets: int
    total_tokens: int
