"""Query Executor implementing QueryExecutorPort."""

import time

from ria.domain.index.value_objects import FilePath
from ria.domain.query.entities import (
    CallHierarchyResult,
    DefinitionResult,
    DependencyResult,
    ExportResult,
    ImportResult,
    ModuleSearchResult,
    QueryResult,
    QueryResultPayload,
    ReferenceResult,
    SymbolSearchResult,
)
from ria.domain.query.value_objects import QueryPlan, QueryStatistics, QueryType
from ria.domain.resolution.entities import SemanticSymbol
from ria.domain.resolution.value_objects import (
    CallRelation,
    ImportRelation,
    RelationKind,
    SemanticDefinition,
    SemanticReference,
    SymbolKind,
)
from ria.domain.sync.value_objects import CommitReference, RepositoryIdentity
from ria.ports.query.executor import QueryExecutorPort
from ria.ports.storage.fact_store import FactStorePort
from ria.query.exceptions import QueryExecutionException


class QueryExecutor(QueryExecutorPort):
    """Executor querying FactStorePort abstraction to evaluate logical QueryPlans."""

    def execute_plan(
        self,
        plan: QueryPlan,
        fact_store: FactStorePort,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
    ) -> QueryResult:
        start_t = time.perf_counter()
        qtype = plan.query_type
        criteria = plan.criteria

        try:
            symbols = fact_store.get_symbols(repo_id, commit, path=criteria.file_path)
            relations = fact_store.get_relations(
                repo_id, commit, source_moniker=criteria.symbol_moniker
            )
            scanned_records = len(symbols) + len(relations)

            payload: QueryResultPayload

            if qtype == QueryType.GO_TO_DEFINITION:
                matched_symbols: list[SemanticSymbol] = []
                matched_defs: list[SemanticDefinition] = []
                for sym in symbols:
                    if (
                        criteria.symbol_moniker
                        and sym.moniker == criteria.symbol_moniker
                    ) or (criteria.symbol_name and sym.name == criteria.symbol_name):
                        matched_symbols.append(sym)
                        matched_defs.append(
                            SemanticDefinition(
                                moniker=sym.moniker,
                                qualified_name=sym.qualified_name,
                                path=sym.path,
                                location=sym.location,
                            )
                        )
                        if len(matched_symbols) >= criteria.max_results:
                            break

                payload = DefinitionResult(
                    symbols=tuple(matched_symbols),
                    definitions=tuple(matched_defs),
                )

            elif qtype == QueryType.FIND_REFERENCES:
                matched_refs: list[SemanticReference] = []
                fallback_path = criteria.file_path or (
                    symbols[0].path if symbols else FilePath(relative_path="unknown")
                )
                for rel in relations:
                    if rel.kind == RelationKind.REFERENCES:
                        matched_refs.append(
                            SemanticReference(
                                source_moniker=rel.source,
                                target_moniker=rel.target,
                                path=fallback_path,
                                location=rel.location,
                            )
                        )
                        if len(matched_refs) >= criteria.max_results:
                            break
                payload = ReferenceResult(references=tuple(matched_refs))

            elif qtype in (QueryType.FIND_CALLERS, QueryType.FIND_CALLEES):
                matched_calls: list[CallRelation] = []
                all_rels = fact_store.get_relations(repo_id, commit)
                scanned_records += len(all_rels)

                for rel in all_rels:
                    if rel.kind == RelationKind.CALLS:
                        if qtype == QueryType.FIND_CALLERS and (
                            criteria.symbol_moniker is None
                            or rel.target == criteria.symbol_moniker
                        ):
                            matched_calls.append(
                                CallRelation(
                                    caller_moniker=rel.source,
                                    callee_moniker=rel.target,
                                    location=rel.location,
                                )
                            )
                        elif qtype == QueryType.FIND_CALLEES and (
                            criteria.symbol_moniker is None
                            or rel.source == criteria.symbol_moniker
                        ):
                            matched_calls.append(
                                CallRelation(
                                    caller_moniker=rel.source,
                                    callee_moniker=rel.target,
                                    location=rel.location,
                                )
                            )

                        if len(matched_calls) >= criteria.max_results:
                            break
                payload = CallHierarchyResult(calls=tuple(matched_calls))

            elif qtype == QueryType.FIND_IMPORTS:
                matched_imps: list[ImportRelation] = []
                fallback_path = criteria.file_path or (
                    symbols[0].path if symbols else FilePath(relative_path="unknown")
                )
                for rel in relations:
                    if rel.kind == RelationKind.IMPORTS:
                        matched_imps.append(
                            ImportRelation(
                                importer_path=fallback_path,
                                imported_symbol_moniker=rel.target,
                            )
                        )
                        if len(matched_imps) >= criteria.max_results:
                            break
                payload = ImportResult(imports=tuple(matched_imps))

            elif qtype == QueryType.FIND_EXPORTS:
                matched_exp: list[SemanticSymbol] = []
                for sym in symbols:
                    if sym.modifiers.is_exported:
                        matched_exp.append(sym)
                        if len(matched_exp) >= criteria.max_results:
                            break
                payload = ExportResult(exports=tuple(matched_exp))

            elif qtype == QueryType.DEPENDENCY_ANALYSIS:
                payload = DependencyResult(
                    relations=tuple(relations[: criteria.max_results])
                )

            elif qtype == QueryType.SYMBOL_SEARCH:
                matched_syms: list[SemanticSymbol] = []
                query_name = (criteria.symbol_name or "").lower()
                for sym in symbols:
                    if not query_name or query_name in sym.name.lower():
                        matched_syms.append(sym)
                        if len(matched_syms) >= criteria.max_results:
                            break
                payload = SymbolSearchResult(symbols=tuple(matched_syms))

            elif qtype == QueryType.MODULE_SEARCH:
                matched_mods: list[SemanticSymbol] = []
                query_name = (criteria.symbol_name or "").lower()
                for sym in symbols:
                    if sym.kind == SymbolKind.MODULE and (
                        not query_name or query_name in sym.name.lower()
                    ):
                        matched_mods.append(sym)
                        if len(matched_mods) >= criteria.max_results:
                            break
                payload = ModuleSearchResult(modules=tuple(matched_mods))

            else:
                raise QueryExecutionException(f"Unsupported QueryType '{qtype}'.")

            elapsed_ms = (time.perf_counter() - start_t) * 1000.0
            stats = QueryStatistics(
                planning_duration_ms=0.5,
                execution_duration_ms=elapsed_ms,
                total_records_scanned=scanned_records,
                cache_hit=False,
            )

            return QueryResult(
                query_id=plan.query_id,
                query_type=qtype,
                payload=payload,
                statistics=stats,
                is_success=True,
            )
        except Exception as err:
            elapsed_ms = (time.perf_counter() - start_t) * 1000.0
            stats = QueryStatistics(
                planning_duration_ms=0.5,
                execution_duration_ms=elapsed_ms,
                total_records_scanned=0,
            )
            return QueryResult(
                query_id=plan.query_id,
                query_type=qtype,
                payload=None,
                statistics=stats,
                is_success=False,
                error_message=f"Query execution failed: {err}",
            )
