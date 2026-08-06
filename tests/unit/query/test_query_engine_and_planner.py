"""Unit tests for C4 Query Engine domain models, planner, executor, optimizer, cache, engine, and use cases."""

from pathlib import Path

import pytest
from ria.application.query import (
    CallHierarchyQueryDTO,
    DependencyAnalysisUseCase,
    DependencyQueryDTO,
    FindCallHierarchyUseCase,
    FindDefinitionQueryDTO,
    FindDefinitionUseCase,
    FindReferencesQueryDTO,
    FindReferencesUseCase,
    QueryApplicationService,
    SearchSymbolQueryDTO,
    SearchSymbolUseCase,
)
from ria.domain.common.value_objects import Timestamp, UUIDv4
from ria.domain.index.value_objects import FilePath, Location
from ria.domain.query import (
    CallHierarchyResult,
    DefinitionResult,
    DependencyResult,
    ExportResult,
    ImportResult,
    InvalidQueryCriteriaError,
    ModuleSearchResult,
    Query,
    QueryCriteria,
    QueryPlan,
    QueryType,
    ReferenceResult,
    SymbolSearchResult,
)
from ria.domain.resolution import (
    CallRelation,
    ImportRelation,
    QualifiedName,
    RelationKind,
    ResolvedFactSet,
    SemanticDefinition,
    SemanticReference,
    SemanticRelation,
    SemanticSymbol,
    SymbolKind,
    SymbolModifiers,
    SymbolMoniker,
    Visibility,
)
from ria.domain.sync import CommitReference, RepositoryIdentity, RepositoryState, SyncStatus
from ria.infrastructure.storage import SQLiteFactStoreAdapter, SQLiteRepositoryRegistryAdapter
from ria.infrastructure.system import InMemoryMetricsAdapter, StandardLoggerAdapter, SystemClockAdapter
from ria.query import (
    QueryCache,
    QueryEngine,
    QueryExecutor,
    QueryOptimizer,
    QueryPlanner,
)


def test_query_planner_and_optimizer() -> None:
    planner = QueryPlanner()
    optimizer = QueryOptimizer()

    criteria = QueryCriteria(symbol_name=" main ", max_results=2000)
    query = Query(query_id="q1", query_type=QueryType.GO_TO_DEFINITION, criteria=criteria)

    plan = planner.create_plan(query)
    assert plan.query_id == "q1"
    assert plan.query_type == QueryType.GO_TO_DEFINITION

    opt_plan = optimizer.optimize_plan(plan)
    assert opt_plan.criteria.symbol_name == "main"
    assert opt_plan.criteria.max_results == 1000  # Bounded max

    with pytest.raises(InvalidQueryCriteriaError):
        QueryCriteria(max_results=0)


def test_query_cache() -> None:
    cache = QueryCache(enabled=True)

    repo_id = RepositoryIdentity(repo_id=UUIDv4.generate(), remote_url="https://github.com/org/repo.git", name="repo")
    commit = CommitReference(sha="a" * 40, committed_at=Timestamp.now())
    plan = QueryPlan(query_id="q1", query_type=QueryType.SYMBOL_SEARCH, criteria=QueryCriteria(symbol_name="login"))

    assert cache.get(repo_id, commit, plan) is None

    cache.clear()


def test_query_executor_evaluation_all_types() -> None:
    fact_store = SQLiteFactStoreAdapter(db_path=":memory:")
    repo_id = RepositoryIdentity(repo_id=UUIDv4.generate(), remote_url="https://github.com/org/repo.git", name="repo")
    commit = CommitReference(sha="b" * 40, committed_at=Timestamp.now())

    fp = FilePath(relative_path="auth.py")
    loc = Location(1, 0, 3, 10)
    moniker = SymbolMoniker(value="repo:auth.py:global:login")
    qname = QualifiedName(dotted_path="auth.login")

    sym_func = SemanticSymbol(
        moniker=moniker,
        name="login",
        qualified_name=qname,
        kind=SymbolKind.FUNCTION,
        visibility=Visibility.PUBLIC,
        path=fp,
        location=loc,
        modifiers=SymbolModifiers(is_exported=True),
    )
    sym_mod = SemanticSymbol(
        moniker=SymbolMoniker(value="repo:auth.py:global:auth"),
        name="auth",
        qualified_name=QualifiedName(dotted_path="auth"),
        kind=SymbolKind.MODULE,
        visibility=Visibility.PUBLIC,
        path=fp,
        location=loc,
    )
    defn = SemanticDefinition(moniker=moniker, qualified_name=qname, path=fp, location=loc)

    callee_m = SymbolMoniker(value="repo:auth.py:global:hash_password")
    call_rel = CallRelation(caller_moniker=moniker, callee_moniker=callee_m, location=loc)
    imp_rel = ImportRelation(importer_path=fp, imported_symbol_moniker=callee_m)
    gen_rel = SemanticRelation(source=moniker, target=callee_m, kind=RelationKind.REFERENCES, location=loc)

    fact_set = ResolvedFactSet(
        symbols=(sym_func, sym_mod),
        definitions=(defn,),
        calls=(call_rel,),
        imports=(imp_rel,),
        relations=(gen_rel,),
    )
    fact_store.save_fact_set(repo_id, commit, fact_set)

    planner = QueryPlanner()
    executor = QueryExecutor()
    optimizer = QueryOptimizer()
    cache = QueryCache()

    engine = QueryEngine(planner, executor, optimizer, cache)

    # 1. Definition Query
    def_q = Query(query_id="q1", query_type=QueryType.GO_TO_DEFINITION, criteria=QueryCriteria(symbol_name="login"))
    def_res = engine.execute_query(def_q, fact_store, repo_id, commit)
    assert def_res.is_success
    assert isinstance(def_res.payload, DefinitionResult)
    assert len(def_res.payload.symbols) == 1

    # 2. References Query
    ref_q = Query(query_id="q2", query_type=QueryType.FIND_REFERENCES, criteria=QueryCriteria(symbol_moniker=moniker))
    ref_res = engine.execute_query(ref_q, fact_store, repo_id, commit)
    assert ref_res.is_success
    assert isinstance(ref_res.payload, ReferenceResult)
    assert len(ref_res.payload.references) == 1

    # 3. Callers Query
    callers_q = Query(query_id="q3", query_type=QueryType.FIND_CALLERS, criteria=QueryCriteria(symbol_moniker=callee_m))
    callers_res = engine.execute_query(callers_q, fact_store, repo_id, commit)
    assert callers_res.is_success
    assert isinstance(callers_res.payload, CallHierarchyResult)
    assert len(callers_res.payload.calls) == 1

    # 4. Callees Query
    callees_q = Query(query_id="q4", query_type=QueryType.FIND_CALLEES, criteria=QueryCriteria(symbol_moniker=moniker))
    callees_res = engine.execute_query(callees_q, fact_store, repo_id, commit)
    assert callees_res.is_success
    assert isinstance(callees_res.payload, CallHierarchyResult)
    assert len(callees_res.payload.calls) == 1

    # 5. Imports Query
    imp_q = Query(query_id="q5", query_type=QueryType.FIND_IMPORTS, criteria=QueryCriteria(symbol_moniker=moniker))
    imp_res = engine.execute_query(imp_q, fact_store, repo_id, commit)
    assert imp_res.is_success
    assert isinstance(imp_res.payload, ImportResult)

    # 6. Exports Query
    exp_q = Query(query_id="q6", query_type=QueryType.FIND_EXPORTS, criteria=QueryCriteria(file_path=fp))
    exp_res = engine.execute_query(exp_q, fact_store, repo_id, commit)
    assert exp_res.is_success
    assert isinstance(exp_res.payload, ExportResult)
    assert len(exp_res.payload.exports) == 1

    # 7. Dependency Query
    dep_q = Query(query_id="q7", query_type=QueryType.DEPENDENCY_ANALYSIS, criteria=QueryCriteria(symbol_moniker=moniker))
    dep_res = engine.execute_query(dep_q, fact_store, repo_id, commit)
    assert dep_res.is_success
    assert isinstance(dep_res.payload, DependencyResult)

    # 8. Symbol Search Query
    srch_q = Query(query_id="q8", query_type=QueryType.SYMBOL_SEARCH, criteria=QueryCriteria(symbol_name="log"))
    srch_res = engine.execute_query(srch_q, fact_store, repo_id, commit)
    assert srch_res.is_success
    assert isinstance(srch_res.payload, SymbolSearchResult)

    # 9. Module Search Query
    mod_q = Query(query_id="q9", query_type=QueryType.MODULE_SEARCH, criteria=QueryCriteria(symbol_name="auth"))
    mod_res = engine.execute_query(mod_q, fact_store, repo_id, commit)
    assert mod_res.is_success
    assert isinstance(mod_res.payload, ModuleSearchResult)
    assert len(mod_res.payload.modules) == 1


def test_query_application_use_cases() -> None:
    fact_store = SQLiteFactStoreAdapter(db_path=":memory:")
    registry = SQLiteRepositoryRegistryAdapter(db_path=":memory:")
    clock = SystemClockAdapter()
    logger = StandardLoggerAdapter("test")
    metrics = InMemoryMetricsAdapter()

    repo_id_val = str(UUIDv4.generate().value)
    repo_identity = RepositoryIdentity(repo_id=UUIDv4(value=repo_id_val), remote_url="https://github.com/org/repo.git", name="repo")
    commit = CommitReference(sha="c" * 40, committed_at=Timestamp.now())

    from ria.domain.sync import RepositoryMetadata
    meta = RepositoryMetadata(file_count=1, total_bytes=100, default_branch="main", registered_at=Timestamp.now())
    state = RepositoryState(identity=repo_identity, status=SyncStatus.SYNCHRONIZED, metadata=meta)
    state.mark_synchronized(branch=None, commit=commit, synced_at=Timestamp.now())
    registry.save_state(state)

    planner = QueryPlanner()
    executor = QueryExecutor()
    optimizer = QueryOptimizer()
    cache = QueryCache()
    engine = QueryEngine(planner, executor, optimizer, cache)

    query_service = QueryApplicationService(engine, fact_store, registry, clock, logger, metrics)

    find_def_uc = FindDefinitionUseCase(query_service)
    find_ref_uc = FindReferencesUseCase(query_service)
    call_hier_uc = FindCallHierarchyUseCase(query_service)
    search_sym_uc = SearchSymbolUseCase(query_service)
    dep_uc = DependencyAnalysisUseCase(query_service)

    res_def = find_def_uc.execute(FindDefinitionQueryDTO(repo_id=repo_id_val, symbol_name="unknown"))
    assert res_def.is_success

    res_ref = find_ref_uc.execute(FindReferencesQueryDTO(repo_id=repo_id_val, symbol_moniker="m1"))
    assert res_ref.is_success

    res_call = call_hier_uc.execute(CallHierarchyQueryDTO(repo_id=repo_id_val, symbol_moniker="m1"))
    assert res_call.is_success

    res_srch = search_sym_uc.execute(SearchSymbolQueryDTO(repo_id=repo_id_val, symbol_name="test"))
    assert res_srch.is_success

    res_dep = dep_uc.execute(DependencyQueryDTO(repo_id=repo_id_val))
    assert res_dep.is_success
