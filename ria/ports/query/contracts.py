"""Canonical ports for the Repository Query & Analysis Engine."""

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


@runtime_checkable
class QueryEnginePort(Protocol):
    def execute_query(
        self, twin: RepositoryTwin, request: QueryRequest
    ) -> QueryResult: ...


@runtime_checkable
class SymbolQueryPort(Protocol):
    def find_symbol(
        self, twin: RepositoryTwin, symbol_name: str
    ) -> Tuple[QueryMatch, ...]: ...

    def find_definition(
        self, twin: RepositoryTwin, symbol_name: str
    ) -> Optional[QueryMatch]: ...

    def find_declaration(
        self, twin: RepositoryTwin, symbol_name: str
    ) -> Optional[QueryMatch]: ...

    def find_scope(
        self, twin: RepositoryTwin, scope_name: str
    ) -> Optional[QueryMatch]: ...

    def find_namespace(
        self, twin: RepositoryTwin, namespace_name: str
    ) -> Optional[QueryMatch]: ...

    def find_references(
        self, twin: RepositoryTwin, symbol_name: str
    ) -> Tuple[QueryMatch, ...]: ...

    def find_overrides(
        self, twin: RepositoryTwin, method_name: str
    ) -> Tuple[QueryMatch, ...]: ...

    def find_implementations(
        self, twin: RepositoryTwin, interface_name: str
    ) -> Tuple[QueryMatch, ...]: ...


@runtime_checkable
class GraphQueryPort(Protocol):
    def node_lookup(
        self, twin: RepositoryTwin, node_id: str
    ) -> Optional[QueryMatch]: ...

    def edge_lookup(
        self, twin: RepositoryTwin, edge_id: str
    ) -> Optional[QueryMatch]: ...

    def neighbour_lookup(
        self, twin: RepositoryTwin, node_id: str
    ) -> Tuple[QueryMatch, ...]: ...

    def shortest_path(
        self, twin: RepositoryTwin, source_id: str, target_id: str
    ) -> Tuple[QueryMatch, ...]: ...

    def reachability(
        self, twin: RepositoryTwin, source_id: str
    ) -> Tuple[QueryMatch, ...]: ...

    def ancestors(
        self, twin: RepositoryTwin, node_id: str
    ) -> Tuple[QueryMatch, ...]: ...

    def descendants(
        self, twin: RepositoryTwin, node_id: str
    ) -> Tuple[QueryMatch, ...]: ...


@runtime_checkable
class DependencyAnalysisPort(Protocol):
    def analyze_dependencies(self, twin: RepositoryTwin) -> DependencyAnalysis: ...


@runtime_checkable
class ImpactAnalysisPort(Protocol):
    def analyze_impact(
        self, twin: RepositoryTwin, changed_files: Tuple[str, ...]
    ) -> ImpactAnalysis: ...


@runtime_checkable
class ArchitectureAnalysisPort(Protocol):
    def analyze_architecture(self, twin: RepositoryTwin) -> ArchitectureAnalysis: ...


@runtime_checkable
class PatternMatchingPort(Protocol):
    def match_patterns(
        self, twin: RepositoryTwin, pattern_type: str, pattern_expression: str
    ) -> Tuple[PatternMatch, ...]: ...


@runtime_checkable
class CrossReferencePort(Protocol):
    def get_cross_references(
        self, twin: RepositoryTwin, symbol_name: str
    ) -> Tuple[CrossReference, ...]: ...


@runtime_checkable
class QueryCacheStore(Protocol):
    def get(self, key: QueryCacheKey) -> Optional[QueryResult]: ...

    def put(self, key: QueryCacheKey, result: QueryResult) -> None: ...

    def invalidate_by_commit(self, commit_sha: CommitSha) -> int: ...


@runtime_checkable
class QueryRegistryPort(Protocol):
    def engine_version(self) -> ComponentVersion: ...

    def supported_query_types(self) -> FrozenSet[str]: ...
