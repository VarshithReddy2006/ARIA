"""Semantic resolution results, statistics, diagnostics, and timing domain models.

Encapsulates all outputs produced by semantic resolution for a file or commit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Tuple

from ria.domain.enums import DiagnosticSeverity
from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.inheritance import InheritanceRelation, OverrideRelation
from ria.domain.models.namespace import Namespace
from ria.domain.models.scope import Scope
from ria.domain.models.span import SourceSpan
from ria.domain.models.symbol import Symbol
from ria.domain.models.symbol_reference import SymbolReference

__all__ = [
    "ResolutionDiagnostic",
    "ResolutionStatistics",
    "ResolutionTiming",
    "ResolutionMetadata",
    "ResolutionResult",
]


@dataclass(frozen=True)
class ResolutionDiagnostic:
    """Diagnostic produced during semantic resolution.

    Attributes:
        severity: DiagnosticSeverity (info, warning, error).
        message: Descriptive explanation.
        span: Optional SourceSpan location.
        code: Diagnostic error code string.
    """

    severity: DiagnosticSeverity
    message: str
    span: Optional[SourceSpan] = None
    code: str = "SEMANTIC_ERROR"

    def __post_init__(self) -> None:
        if not self.message or not self.message.strip():
            raise ValueError("diagnostic message must be non-empty")
        if not self.code or not self.code.strip():
            raise ValueError("diagnostic code must be non-empty")


@dataclass(frozen=True)
class ResolutionStatistics:
    """Aggregate statistics produced by semantic resolution.

    Attributes:
        symbols_total: Count of symbols extracted.
        scopes_total: Count of lexical scopes built.
        namespaces_total: Count of namespaces built.
        references_total: Total symbol references identified.
        references_resolved: Count of symbol references successfully resolved.
        inheritance_relations_total: Count of inheritance relations identified.
        override_relations_total: Count of method override relations identified.
        diagnostics_total: Count of diagnostics produced.
    """

    symbols_total: int = 0
    scopes_total: int = 0
    namespaces_total: int = 0
    references_total: int = 0
    references_resolved: int = 0
    inheritance_relations_total: int = 0
    override_relations_total: int = 0
    diagnostics_total: int = 0

    def __post_init__(self) -> None:
        for name in (
            "symbols_total",
            "scopes_total",
            "namespaces_total",
            "references_total",
            "references_resolved",
            "inheritance_relations_total",
            "override_relations_total",
            "diagnostics_total",
        ):
            val = getattr(self, name)
            if val < 0:
                raise ValueError(f"{name} must be non-negative, got {val}")
        if self.references_resolved > self.references_total:
            raise ValueError(
                f"references_resolved ({self.references_resolved}) cannot exceed "
                f"references_total ({self.references_total})"
            )

    @property
    def resolution_pct(self) -> float:
        """Percentage of references successfully resolved."""
        if self.references_total == 0:
            return 100.0
        return 100.0 * self.references_resolved / self.references_total


@dataclass(frozen=True)
class ResolutionTiming:
    """Timing breakdown of semantic resolution steps in seconds.

    Attributes:
        scope_seconds: Time spent building lexical scopes.
        symbol_seconds: Time spent extracting symbols.
        import_seconds: Time spent resolving imports/exports.
        reference_seconds: Time spent resolving identifier references.
        inheritance_seconds: Time spent resolving subtyping/inheritance.
        total_seconds: Aggregate wall-clock resolution time.
    """

    scope_seconds: float = 0.0
    symbol_seconds: float = 0.0
    import_seconds: float = 0.0
    reference_seconds: float = 0.0
    inheritance_seconds: float = 0.0
    total_seconds: float = 0.0

    def __post_init__(self) -> None:
        for name in (
            "scope_seconds",
            "symbol_seconds",
            "import_seconds",
            "reference_seconds",
            "inheritance_seconds",
            "total_seconds",
        ):
            val = getattr(self, name)
            if val < 0.0:
                raise ValueError(f"{name} must be non-negative, got {val}")


@dataclass(frozen=True)
class ResolutionMetadata:
    """Metadata describing a semantic resolution execution context.

    Attributes:
        repository_id: Owning repository.
        commit_sha: Commit SHA under analysis.
        language: Canonical language name.
        resolved_at: Timestamp when resolution ran.
    """

    repository_id: RepositoryId
    commit_sha: CommitSha
    language: str
    resolved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.language or not self.language.strip():
            raise ValueError("language must be non-empty")


@dataclass(frozen=True)
class ResolutionResult:
    """Immutable composite result of semantic resolution over a file or commit unit.

    Attributes:
        symbols: Tuple of extracted symbols.
        scopes: Tuple of built lexical scopes.
        namespaces: Tuple of namespaces.
        references: Tuple of symbol references.
        inheritance_relations: Tuple of subtyping/inheritance relations.
        override_relations: Tuple of method override relations.
        diagnostics: Tuple of resolution diagnostics.
        statistics: ResolutionStatistics summary.
        timing: ResolutionTiming breakdown.
        from_cache: Whether this result was retrieved from cache.
    """

    symbols: Tuple[Symbol, ...] = field(default_factory=tuple)
    scopes: Tuple[Scope, ...] = field(default_factory=tuple)
    namespaces: Tuple[Namespace, ...] = field(default_factory=tuple)
    references: Tuple[SymbolReference, ...] = field(default_factory=tuple)
    inheritance_relations: Tuple[InheritanceRelation, ...] = field(
        default_factory=tuple
    )
    override_relations: Tuple[OverrideRelation, ...] = field(default_factory=tuple)
    diagnostics: Tuple[ResolutionDiagnostic, ...] = field(default_factory=tuple)
    statistics: ResolutionStatistics = field(default_factory=ResolutionStatistics)
    timing: ResolutionTiming = field(default_factory=ResolutionTiming)
    from_cache: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbols", tuple(self.symbols))
        object.__setattr__(self, "scopes", tuple(self.scopes))
        object.__setattr__(self, "namespaces", tuple(self.namespaces))
        object.__setattr__(self, "references", tuple(self.references))
        object.__setattr__(
            self, "inheritance_relations", tuple(self.inheritance_relations)
        )
        object.__setattr__(self, "override_relations", tuple(self.override_relations))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
