"""End-to-End Integration Test for C4 Query Engine Pipeline & Performance Targets."""

import subprocess
import time
from pathlib import Path

from ria.application.index import (
    FileDiscovery,
    IndexBatchAssembler,
    IndexPipeline,
    IndexUnitBuilder,
    LanguageDetection,
    RepositoryScanner,
)
from ria.application.query import (
    DependencyAnalysisUseCase,
    DependencyQueryDTO,
    FindCallHierarchyUseCase,
    FindDefinitionQueryDTO,
    FindDefinitionUseCase,
    QueryApplicationService,
    SearchSymbolQueryDTO,
    SearchSymbolUseCase,
)
from ria.application.resolution import ResolveAndStoreCommand, ResolveAndStoreUseCase, ResolutionApplicationService
from ria.application.sync import (
    RegisterRepositoryCommand,
    RegisterRepositoryUseCase,
    SynchronizeRepositoryCommand,
    SynchronizeRepositoryUseCase,
)
from ria.config import Container, Settings
from ria.domain.index.value_objects import Language
from ria.domain.query.entities import DefinitionResult, DependencyResult, SymbolSearchResult
from ria.infrastructure.storage import SQLiteFactStoreAdapter
from ria.plugins import PluginLoader, PluginRegistry, JavaScriptTreeSitterPlugin, PythonTreeSitterPlugin, TypeScriptTreeSitterPlugin
from ria.query import QueryCache, QueryEngine, QueryExecutor, QueryOptimizer, QueryPlanner
from ria.resolution import (
    JavaScriptLanguageResolver,
    LanguageResolverRegistry,
    PythonLanguageResolver,
    ResolutionEngine,
    TypeScriptLanguageResolver,
)


def test_full_query_engine_end_to_end_pipeline(tmp_path: Path) -> None:
    """End-to-End Pipeline & Performance Verification Test:
    Git -> Sync -> Index -> Resolve -> FactStore -> Query Engine.
    """
    # 1. Prepare git origin
    origin_dir = tmp_path / "query_origin"
    origin_dir.mkdir()
    subprocess.run(["git", "init"], cwd=origin_dir, check=True)
    subprocess.run(["git", "config", "user.name", "TestRunner"], cwd=origin_dir, check=True)
    subprocess.run(["git", "config", "user.email", "runner@test.com"], cwd=origin_dir, check=True)

    py_file = origin_dir / "user_service.py"
    py_file.write_text("class UserService:\n    def get_user(self, user_id: str) -> str:\n        return 'user'\n")

    subprocess.run(["git", "add", "."], cwd=origin_dir, check=True)
    subprocess.run(["git", "commit", "-m", "Query test commit"], cwd=origin_dir, check=True)

    # 2. DI Setup
    settings = Settings.create_testing(tmp_path)
    container = Container.create(settings)

    from ria.application.sync import RepositorySyncService
    sync_service = RepositorySyncService(
        git_client=container.git_client,
        registry=container.repository_registry,
        lock_manager=container.repository_lock,
        workspace_manager=container.workspace_manager,
        clock=container.clock,
        logger=container.logger,
        metrics=container.metrics,
    )
    reg_use_case = RegisterRepositoryUseCase(sync_service)
    sync_use_case = SynchronizeRepositoryUseCase(sync_service)

    status_dto = reg_use_case.execute(RegisterRepositoryCommand(remote_url=str(origin_dir), name="query_origin"))
    sync_dto = sync_use_case.execute(SynchronizeRepositoryCommand(repo_id=status_dto.repo_id))
    assert sync_dto.is_success

    # 3. Setup Index & Resolution Pipelines
    discovery = FileDiscovery(filesystem=container.filesystem)
    lang_detect = LanguageDetection(filesystem=container.filesystem)
    scanner = RepositoryScanner(discovery, lang_detect, container.filesystem, container.hashing)

    plugin_registry = PluginRegistry()
    loader = PluginLoader(plugin_registry)
    loader.load_plugin_class(PythonTreeSitterPlugin)
    loader.load_plugin_class(TypeScriptTreeSitterPlugin)
    loader.load_plugin_class(JavaScriptTreeSitterPlugin)

    builder = IndexUnitBuilder()
    assembler = IndexBatchAssembler()

    pipeline = IndexPipeline(
        scanner=scanner,
        parser_registry=plugin_registry,
        unit_builder=builder,
        batch_assembler=assembler,
        registry=container.repository_registry,
        workspace_manager=container.workspace_manager,
        filesystem=container.filesystem,
        clock=container.clock,
        logger=container.logger,
        metrics=container.metrics,
    )

    resolver_registry = LanguageResolverRegistry()
    resolver_registry.register_resolver(Language.PYTHON, PythonLanguageResolver())
    resolver_registry.register_resolver(Language.TYPESCRIPT, TypeScriptLanguageResolver())
    resolver_registry.register_resolver(Language.JAVASCRIPT, JavaScriptLanguageResolver())

    res_engine = ResolutionEngine(resolver_registry=resolver_registry)
    fact_store = SQLiteFactStoreAdapter(db_path=tmp_path / "fact_store.db")

    res_service = ResolutionApplicationService(
        index_pipeline=pipeline,
        resolution_engine=res_engine,
        fact_store=fact_store,
        registry=container.repository_registry,
        clock=container.clock,
        logger=container.logger,
        metrics=container.metrics,
    )
    res_use_case = ResolveAndStoreUseCase(res_service)
    fact_dto = res_use_case.execute(ResolveAndStoreCommand(repo_id=status_dto.repo_id))
    assert fact_dto.is_success

    # 4. Setup Query Engine & Application Service
    planner = QueryPlanner()
    executor = QueryExecutor()
    optimizer = QueryOptimizer()
    cache = QueryCache()
    query_engine = QueryEngine(planner, executor, optimizer, cache)

    query_service = QueryApplicationService(
        query_engine=query_engine,
        fact_store=fact_store,
        registry=container.repository_registry,
        clock=container.clock,
        logger=container.logger,
        metrics=container.metrics,
    )

    find_def_uc = FindDefinitionUseCase(query_service)
    search_sym_uc = SearchSymbolUseCase(query_service)
    dep_uc = DependencyAnalysisUseCase(query_service)

    # 5. Evaluate Queries & Assert Performance Targets
    # Warm-up lookup
    _ = find_def_uc.execute(FindDefinitionQueryDTO(repo_id=status_dto.repo_id, symbol_name="UserService"))

    t0 = time.perf_counter()
    def_res = find_def_uc.execute(FindDefinitionQueryDTO(repo_id=status_dto.repo_id, symbol_name="UserService"))
    def_lat_ms = (time.perf_counter() - t0) * 1000.0

    assert def_res.is_success
    assert isinstance(def_res.payload, DefinitionResult)
    assert len(def_res.payload.symbols) == 1
    assert def_res.payload.symbols[0].name == "UserService"
    assert def_lat_ms < 5.0, f"Definition lookup latency {def_lat_ms:.2f}ms exceeded target of 5.0ms"

    # Symbol Search
    srch_res = search_sym_uc.execute(SearchSymbolQueryDTO(repo_id=status_dto.repo_id, symbol_name="user"))
    assert srch_res.is_success
    assert isinstance(srch_res.payload, SymbolSearchResult)
    assert len(srch_res.payload.symbols) >= 1

    # Dependency Analysis
    t0 = time.perf_counter()
    dep_res = dep_uc.execute(DependencyQueryDTO(repo_id=status_dto.repo_id))
    dep_lat_ms = (time.perf_counter() - t0) * 1000.0

    assert dep_res.is_success
    assert isinstance(dep_res.payload, DependencyResult)
    assert dep_lat_ms < 30.0, f"Dependency query latency {dep_lat_ms:.2f}ms exceeded target of 30.0ms"
