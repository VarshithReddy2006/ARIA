"""Port protocols for Milestone 7 — Repository Query & Analysis Engine.

Defines runtime checkable protocols for symbol querying, graph querying, dependency analysis,
impact analysis, architecture analysis, pattern matching, cross-referencing, query optimization,
query caching, and query registry.
"""

from __future__ import annotations

from typing import FrozenSet, Optional, Protocol, Tuple, runtime_checkable

from ria.domain.identity import CommitSha
from ria.domain.models.analysis_models import (
    ArchitectureAnalysis,
    CrossReference,
    DependencyAnalysis,
    ImpactAnalysis,
    PatternMatch,
)
from ria.domain.models.parser_identity import ComponentVersion
from ria.domain.models.query_identity import QueryCacheKey
from ria.domain.models.query_request import QueryRequest
from ria.domain.models.query_result import QueryMatch, QueryResult
from ria.domain.models.repository_twin import RepositoryTwin

__all__ = [
    "QueryEnginePort",
    "SymbolQueryPort",
    "GraphQueryPort",
    "DependencyAnalysisPort",
    "ImpactAnalysisPort",
    "ArchitectureAnalysisPort",
    "PatternMatchingPort",
    "CrossReferencePort",
    "QueryCacheStore",
    "QueryRegistryPort",
]


@runtime_checkable
class QueryEnginePort(Protocol):
    """Port for executing general Repository Query requests."""

    def execute_query(
        self,
        twin: RepositoryTwin,
        request: QueryRequest,
    ) -> QueryResult:
        """Execute a QueryRequest on a RepositoryTwin."""
        ...


@runtime_checkable
class SymbolQueryPort(Protocol):
    """Port for deterministic symbol lookup and resolution queries."""

    def find_symbol(
        self, twin: RepositoryTwin, symbol_name: str
    ) -> Tuple[QueryMatch, ...]:
        """Find symbols matching symbol_name."""
        ...

    def find_definition(
        self, twin: RepositoryTwin, symbol_name: str
    ) -> Optional[QueryMatch]:
        """Find definition site of a symbol."""
        ...

    def find_declaration(
        self, twin: RepositoryTwin, symbol_name: str
    ) -> Optional[QueryMatch]:
        """Find declaration site of a symbol."""
        ...

    def find_scope(self, twin: RepositoryTwin, scope_name: str) -> Optional[QueryMatch]:
        """Find scope matching scope_name."""
        ...

    def find_namespace(
        self, twin: RepositoryTwin, namespace_name: str
    ) -> Optional[QueryMatch]:
        """Find namespace matching namespace_name."""
        ...

    def find_references(
        self, twin: RepositoryTwin, symbol_name: str
    ) -> Tuple[QueryMatch, ...]:
        """Find references to symbol_name."""
        ...

    def find_overrides(
        self, twin: RepositoryTwin, method_name: str
    ) -> Tuple[QueryMatch, ...]:
        """Find method overrides."""
        ...

    def find_implementations(
        self, twin: RepositoryTwin, interface_name: str
    ) -> Tuple[QueryMatch, ...]:
        """Find class implementations of an interface."""
        ...


@runtime_checkable
class GraphQueryPort(Protocol):
    """Port for deterministic graph structure queries on Digital Twin."""

    def node_lookup(self, twin: RepositoryTwin, node_id: str) -> Optional[QueryMatch]:
        """Look up a single graph node."""
        ...

    def edge_lookup(self, twin: RepositoryTwin, edge_id: str) -> Optional[QueryMatch]:
        """Look up a single graph edge."""
        ...

    def neighbour_lookup(
        self, twin: RepositoryTwin, node_id: str
    ) -> Tuple[QueryMatch, ...]:
        """Look up neighboring nodes."""
        ...

    def shortest_path(
        self, twin: RepositoryTwin, source_id: str, target_id: str
    ) -> Tuple[QueryMatch, ...]:
        """Find shortest path between source and target nodes."""
        ...

    def reachability(
        self, twin: RepositoryTwin, source_id: str
    ) -> Tuple[QueryMatch, ...]:
        """Compute set of reachable nodes from source_id."""
        ...

    def ancestors(self, twin: RepositoryTwin, node_id: str) -> Tuple[QueryMatch, ...]:
        """Look up ancestor nodes."""
        ...

    def descendants(self, twin: RepositoryTwin, node_id: str) -> Tuple[QueryMatch, ...]:
        """Look up descendant nodes."""
        ...


@runtime_checkable
class DependencyAnalysisPort(Protocol):
    """Port for module, package, and circular dependency analysis."""

    def analyze_dependencies(self, twin: RepositoryTwin) -> DependencyAnalysis:
        """Perform comprehensive dependency analysis."""
        ...


@runtime_checkable
class ImpactAnalysisPort(Protocol):
    """Port for change impact and ripple analysis."""

    def analyze_impact(
        self,
        twin: RepositoryTwin,
        changed_files: Tuple[str, ...],
    ) -> ImpactAnalysis:
        """Perform change impact analysis for changed files."""
        ...


@runtime_checkable
class ArchitectureAnalysisPort(Protocol):
    """Port for architectural layer and cycle violation analysis."""

    def analyze_architecture(self, twin: RepositoryTwin) -> ArchitectureAnalysis:
        """Perform architectural health analysis."""
        ...


@runtime_checkable
class PatternMatchingPort(Protocol):
    """Port for structural pattern matching searches."""

    def match_patterns(
        self,
        twin: RepositoryTwin,
        pattern_type: str,
        pattern_expression: str,
    ) -> Tuple[PatternMatch, ...]:
        """Perform structural pattern search."""
        ...


@runtime_checkable
class CrossReferencePort(Protocol):
    """Port for cross-reference lookups across codebase."""

    def get_cross_references(
        self,
        twin: RepositoryTwin,
        symbol_name: str,
    ) -> Tuple[CrossReference, ...]:
        """Look up cross-references for a symbol."""
        ...


@runtime_checkable
class QueryCacheStore(Protocol):
    """Port for durable query result caching."""

    def get(self, key: QueryCacheKey) -> Optional[QueryResult]:
        """Retrieve cached QueryResult."""
        ...

    def put(self, key: QueryCacheKey, result: QueryResult) -> None:
        """Cache QueryResult."""
        ...

    def invalidate_by_commit(self, commit_sha: CommitSha) -> int:
        """Invalidate query cache entries for a commit."""
        ...


@runtime_checkable
class QueryRegistryPort(Protocol):
    """Port for tracking query engine version and capabilities."""

    def engine_version(self) -> ComponentVersion:
        """Return ComponentVersion of the query engine."""
        ...

    def supported_query_types(self) -> FrozenSet[str]:
        """Return set of supported query types."""
        ...
