# Milestone 7 — Repository Query & Analysis Engine

**Status:** complete
**Implements:** SDD section 3 (L6 Query & Analysis Layer), QueryRequest, QueryId, QueryContext, QueryResult, QueryMatch, QueryFilter, QueryProjection, QueryStatistics, QueryMetadata, AnalysisResult, DependencyAnalysis, ImpactAnalysis, ArchitectureAnalysis, PatternMatch, CrossReference, QueryFingerprint, QueryCacheKey, 0007 database migration, query cache store, symbol query engine, graph query engine, dependency analysis, impact analysis, architecture analysis, pattern matching engine, cross reference engine, query optimizer, and observability.
**Package:** `ria/`
**Tests:** 957 unit/integration tests passed.

---

## 1. Scope & Architecture

Milestone 7 exposes deterministic query and analysis capabilities built on top of the Repository Digital Twin (`RepositoryTwin`, `GraphSnapshot`).

| Item | Location |
|---|---|
| Domain Models | `QueryRequest`, `QueryId`, `QueryContext`, `QueryResult`, `QueryMatch`, `QueryFilter`, `QueryProjection`, `QueryStatistics`, `QueryMetadata`, `AnalysisResult`, `DependencyAnalysis`, `ImpactAnalysis`, `ArchitectureAnalysis`, `PatternMatch`, `CrossReference`, `QueryFingerprint`, `QueryCacheKey` in `ria/domain/models/` |
| Ports | `QueryEnginePort`, `SymbolQueryPort`, `GraphQueryPort`, `DependencyAnalysisPort`, `ImpactAnalysisPort`, `ArchitectureAnalysisPort`, `PatternMatchingPort`, `CrossReferencePort`, `QueryCacheStore`, `QueryRegistryPort` in `ria/ports/query.py` |
| Symbol Query Engine | `SymbolQueryEngine` in `ria/application/symbol_query_engine.py` |
| Graph Query Engine | `TwinGraphQueryEngine` in `ria/application/graph_query_engine.py` |
| Dependency Analysis | `DependencyAnalysisService` in `ria/application/dependency_analysis_service.py` |
| Impact Analysis | `ImpactAnalysisService` in `ria/application/impact_analysis_service.py` |
| Architecture Analysis | `ArchitectureAnalysisService` in `ria/application/architecture_analysis_service.py` |
| Pattern Matching Engine | `PatternMatchingEngine` in `ria/application/pattern_matching_engine.py` |
| Cross Reference Engine | `CrossReferenceEngine` in `ria/application/cross_reference_engine.py` |
| Query Optimizer | `QueryOptimizer` in `ria/application/query_optimizer.py` |
| Application Services & Facade | `RepositoryQueryService` in `ria/application/query_service.py` |
| Persistence & Query Cache | `SqliteQueryStore`, `SqliteQueryCacheStore` in `ria/infrastructure/storage/sqlite/query_store.py` & `0007_repository_query_engine.sql` |
| Container Integration | `Container` in `ria/container.py` |

---

## 2. Phase-by-Phase Breakdown

1. **Phase 1 (Domain Models)**: Created 17 immutable domain entities and value objects.
2. **Phase 2 (Query Ports)**: Defined 10 hexagonal `@runtime_checkable` `typing.Protocol` ports.
3. **Phase 3 (Symbol Query Engine)**: Built `SymbolQueryEngine` (find symbol, definition, declaration, scope, namespace, references, overrides, implementations).
4. **Phase 4 (Graph Query Engine)**: Built `TwinGraphQueryEngine` (node lookup, edge lookup, neighbour lookup, shortest path, reachability, ancestors, descendants).
5. **Phase 5 (Dependency Analysis)**: Built `DependencyAnalysisService` (module/package dependencies, cycles, import chains, max depth).
6. **Phase 6 (Impact Analysis)**: Built `ImpactAnalysisService` (affected files, symbols, classes, callables, dependency/inheritance/reference ripples).
7. **Phase 7 (Architecture Analysis)**: Built `ArchitectureAnalysisService` (layer violations, dependency violations, cycles, orphans, unused symbols, hotspots).
8. **Phase 8 (Pattern Matching Engine)**: Built `PatternMatchingEngine` (classes, interfaces, methods, imports, inheritance chains, custom structural patterns).
9. **Phase 9 (Cross Reference Engine)**: Built `CrossReferenceEngine` (who calls, references, imports, extends, implements, uses).
10. **Phase 10 (Query Optimizer)**: Built `QueryOptimizer` (cache keys, result caching, execution plan generation).
11. **Phase 11 & 13 (Application Services & Observability)**: Implemented facade `RepositoryQueryService` recording query latency, analysis time, and cache metrics through `MetricsSink`.
12. **Phase 12 (Persistence & Query Cache)**: Created schema migration `0007_repository_query_engine.sql` and durable store adapter `SqliteQueryCacheStore`.
13. **Phase 14 & 15 (Unit & Integration Tests)**: Verified all query components with comprehensive test suites.

---

## 3. Verification Commands

```bash
# Unit & Integration Tests
pytest tests/ria/integration/test_architecture_rules.py tests/ria/unit tests/ria/integration -q   # 957 passed in 2.58s

# Code Formatting & Quality
ruff check ria tests/ria       # All checks passed!
ruff format --check .          # All files clean!
```
