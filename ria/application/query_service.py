"""RepositoryQueryService facade application service (Phases 11 & 13).

Provides unified application interface for symbol queries, graph queries, dependency analysis,
impact analysis, architecture analysis, pattern search, cross references, query optimization,
and observability metrics emission.
"""

from __future__ import annotations

import time
from typing import Optional, Tuple

from ria.application.architecture_analysis_service import ArchitectureAnalysisService
from ria.application.cross_reference_engine import CrossReferenceEngine
from ria.application.dependency_analysis_service import DependencyAnalysisService
from ria.application.graph_query_engine import TwinGraphQueryEngine
from ria.application.impact_analysis_service import ImpactAnalysisService
from ria.application.pattern_matching_engine import PatternMatchingEngine
from ria.application.query_optimizer import QueryOptimizer
from ria.application.symbol_query_engine import SymbolQueryEngine
from ria.domain.models.analysis_models import (
    ArchitectureAnalysis,
    CrossReference,
    DependencyAnalysis,
    ImpactAnalysis,
    PatternMatch,
)
from ria.domain.models.query_request import QueryRequest
from ria.domain.models.query_result import (
    QueryMatch,
    QueryMetadata,
    QueryResult,
    QueryStatistics,
)
from ria.domain.models.repository_twin import RepositoryTwin
from ria.observability.metrics import NullMetricsSink
from ria.ports.metrics import MetricsSink
from ria.ports.query import QueryCacheStore, QueryEnginePort

__all__ = ["RepositoryQueryService"]


class RepositoryQueryService(QueryEnginePort):
    """Facade service unifying all Digital Twin query and analysis capabilities with observability."""

    def __init__(
        self,
        cache_store: Optional[QueryCacheStore] = None,
        metrics_sink: Optional[MetricsSink] = None,
    ) -> None:
        self._cache_store = cache_store
        self._metrics_sink = metrics_sink or NullMetricsSink()

        self._symbol_query = SymbolQueryEngine()
        self._graph_query = TwinGraphQueryEngine()
        self._dependency_analysis = DependencyAnalysisService()
        self._impact_analysis = ImpactAnalysisService()
        self._architecture_analysis = ArchitectureAnalysisService()
        self._pattern_matching = PatternMatchingEngine()
        self._cross_reference = CrossReferenceEngine()
        self._optimizer = QueryOptimizer(cache_store=cache_store)

    def execute_query(
        self,
        twin: RepositoryTwin,
        request: QueryRequest,
    ) -> QueryResult:
        """Execute a QueryRequest with caching and observability."""
        t0 = time.perf_counter()

        cached = self._optimizer.get_cached_result(request)
        if cached is not None:
            self._metrics_sink.increment("ria.query.cache_hits")
            return cached

        self._metrics_sink.increment("ria.query.cache_misses")

        target = request.target_name or ""
        matches: Tuple[QueryMatch, ...] = ()

        if request.query_type == "find_symbol":
            matches = self._symbol_query.find_symbol(twin, target)
        elif request.query_type == "find_references":
            matches = self._symbol_query.find_references(twin, target)
        elif request.query_type == "node_lookup":
            m = self._graph_query.node_lookup(twin, target)
            matches = (m,) if m is not None else ()
        elif request.query_type == "neighbour_lookup":
            matches = self._graph_query.neighbour_lookup(twin, target)

        elapsed = time.perf_counter() - t0
        self._metrics_sink.observe("ria.query.execution_time_seconds", elapsed)

        stats = QueryStatistics(
            total_matches=len(matches), execution_time_seconds=elapsed
        )
        meta = QueryMetadata(
            query_id=request.query_id.value, query_type=request.query_type
        )
        result = QueryResult(matches=matches, statistics=stats, metadata=meta)

        self._optimizer.cache_result(request, result)
        return result

    def analyze_dependencies(self, twin: RepositoryTwin) -> DependencyAnalysis:
        """Analyze module and package dependencies."""
        t0 = time.perf_counter()
        res = self._dependency_analysis.analyze_dependencies(twin)
        elapsed = time.perf_counter() - t0
        self._metrics_sink.observe("ria.analysis.dependency_time_seconds", elapsed)
        return res

    def analyze_impact(
        self, twin: RepositoryTwin, changed_files: Tuple[str, ...]
    ) -> ImpactAnalysis:
        """Analyze change impact for changed files."""
        t0 = time.perf_counter()
        res = self._impact_analysis.analyze_impact(twin, changed_files)
        elapsed = time.perf_counter() - t0
        self._metrics_sink.observe("ria.analysis.impact_time_seconds", elapsed)
        return res

    def analyze_architecture(self, twin: RepositoryTwin) -> ArchitectureAnalysis:
        """Analyze architectural health and violations."""
        t0 = time.perf_counter()
        res = self._architecture_analysis.analyze_architecture(twin)
        elapsed = time.perf_counter() - t0
        self._metrics_sink.observe("ria.analysis.architecture_time_seconds", elapsed)
        return res

    def match_patterns(
        self, twin: RepositoryTwin, pattern_type: str, pattern_expression: str
    ) -> Tuple[PatternMatch, ...]:
        """Search structural patterns."""
        t0 = time.perf_counter()
        matches = self._pattern_matching.match_patterns(
            twin, pattern_type, pattern_expression
        )
        elapsed = time.perf_counter() - t0
        self._metrics_sink.observe("ria.analysis.pattern_time_seconds", elapsed)
        return matches

    def get_cross_references(
        self, twin: RepositoryTwin, symbol_name: str
    ) -> Tuple[CrossReference, ...]:
        """Look up cross-references."""
        t0 = time.perf_counter()
        xrefs = self._cross_reference.get_cross_references(twin, symbol_name)
        elapsed = time.perf_counter() - t0
        self._metrics_sink.observe("ria.analysis.cross_reference_time_seconds", elapsed)
        return xrefs
