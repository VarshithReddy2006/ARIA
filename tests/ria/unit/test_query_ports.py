"""Unit tests for Phase 2 query ports runtime conformance."""

from __future__ import annotations

from typing import FrozenSet, Optional, Tuple

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
from ria.ports.query import (
    ArchitectureAnalysisPort,
    CrossReferencePort,
    DependencyAnalysisPort,
    GraphQueryPort as QueryGraphQueryPort,
    ImpactAnalysisPort,
    PatternMatchingPort,
    QueryCacheStore,
    QueryEnginePort,
    QueryRegistryPort,
    SymbolQueryPort,
)


class DummyQueryEngine:
    def execute_query(self, twin: RepositoryTwin, request: QueryRequest) -> QueryResult:
        return QueryResult()


class DummySymbolQueryEngine:
    def find_symbol(
        self, twin: RepositoryTwin, symbol_name: str
    ) -> Tuple[QueryMatch, ...]:
        return ()

    def find_definition(
        self, twin: RepositoryTwin, symbol_name: str
    ) -> Optional[QueryMatch]:
        return None

    def find_declaration(
        self, twin: RepositoryTwin, symbol_name: str
    ) -> Optional[QueryMatch]:
        return None

    def find_scope(self, twin: RepositoryTwin, scope_name: str) -> Optional[QueryMatch]:
        return None

    def find_namespace(
        self, twin: RepositoryTwin, namespace_name: str
    ) -> Optional[QueryMatch]:
        return None

    def find_references(
        self, twin: RepositoryTwin, symbol_name: str
    ) -> Tuple[QueryMatch, ...]:
        return ()

    def find_overrides(
        self, twin: RepositoryTwin, method_name: str
    ) -> Tuple[QueryMatch, ...]:
        return ()

    def find_implementations(
        self, twin: RepositoryTwin, interface_name: str
    ) -> Tuple[QueryMatch, ...]:
        return ()


class DummyGraphQueryEngine:
    def node_lookup(self, twin: RepositoryTwin, node_id: str) -> Optional[QueryMatch]:
        return None

    def edge_lookup(self, twin: RepositoryTwin, edge_id: str) -> Optional[QueryMatch]:
        return None

    def neighbour_lookup(
        self, twin: RepositoryTwin, node_id: str
    ) -> Tuple[QueryMatch, ...]:
        return ()

    def shortest_path(
        self, twin: RepositoryTwin, source_id: str, target_id: str
    ) -> Tuple[QueryMatch, ...]:
        return ()

    def reachability(
        self, twin: RepositoryTwin, source_id: str
    ) -> Tuple[QueryMatch, ...]:
        return ()

    def ancestors(self, twin: RepositoryTwin, node_id: str) -> Tuple[QueryMatch, ...]:
        return ()

    def descendants(self, twin: RepositoryTwin, node_id: str) -> Tuple[QueryMatch, ...]:
        return ()


class DummyDependencyAnalysis:
    def analyze_dependencies(self, twin: RepositoryTwin) -> DependencyAnalysis:
        return DependencyAnalysis()


class DummyImpactAnalysis:
    def analyze_impact(
        self, twin: RepositoryTwin, changed_files: Tuple[str, ...]
    ) -> ImpactAnalysis:
        return ImpactAnalysis()


class DummyArchitectureAnalysis:
    def analyze_architecture(self, twin: RepositoryTwin) -> ArchitectureAnalysis:
        return ArchitectureAnalysis()


class DummyPatternMatching:
    def match_patterns(
        self, twin: RepositoryTwin, pattern_type: str, pattern_expression: str
    ) -> Tuple[PatternMatch, ...]:
        return ()


class DummyCrossReference:
    def get_cross_references(
        self, twin: RepositoryTwin, symbol_name: str
    ) -> Tuple[CrossReference, ...]:
        return ()


class DummyQueryCacheStore:
    def get(self, key: QueryCacheKey) -> Optional[QueryResult]:
        return None

    def put(self, key: QueryCacheKey, result: QueryResult) -> None:
        pass

    def invalidate_by_commit(self, commit_sha: CommitSha) -> int:
        return 0


class DummyQueryRegistry:
    def engine_version(self) -> ComponentVersion:
        return ComponentVersion("dummy-query", "1.0.0")

    def supported_query_types(self) -> FrozenSet[str]:
        return frozenset({"symbol", "graph", "dependency"})


def test_query_ports_conformance() -> None:
    assert isinstance(DummyQueryEngine(), QueryEnginePort)
    assert isinstance(DummySymbolQueryEngine(), SymbolQueryPort)
    assert isinstance(DummyGraphQueryEngine(), QueryGraphQueryPort)
    assert isinstance(DummyDependencyAnalysis(), DependencyAnalysisPort)
    assert isinstance(DummyImpactAnalysis(), ImpactAnalysisPort)
    assert isinstance(DummyArchitectureAnalysis(), ArchitectureAnalysisPort)
    assert isinstance(DummyPatternMatching(), PatternMatchingPort)
    assert isinstance(DummyCrossReference(), CrossReferencePort)
    assert isinstance(DummyQueryCacheStore(), QueryCacheStore)
    assert isinstance(DummyQueryRegistry(), QueryRegistryPort)
