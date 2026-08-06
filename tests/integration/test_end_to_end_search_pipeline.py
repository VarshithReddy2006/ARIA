"""End-to-End Integration Test for C6 Search Engine Pipeline & Performance Targets."""

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
from ria.application.resolution import (
    ResolveAndStoreCommand,
    ResolveAndStoreUseCase,
    ResolutionApplicationService,
)
from ria.application.search import (
    AutocompleteDTO,
    AutocompleteUseCase,
    SearchApplicationService,
    SearchSymbolDTO,
    SearchSymbolUseCase,
)
from ria.application.sync import (
    RegisterRepositoryCommand,
    RegisterRepositoryUseCase,
    SynchronizeRepositoryCommand,
    SynchronizeRepositoryUseCase,
)
from ria.config import Container, Settings
from ria.domain.index.value_objects import Language
from ria.domain.search.entities import AutocompleteResult
from ria.infrastructure.storage import SQLiteFactStoreAdapter
from ria.plugins import (
    PluginLoader,
    PluginRegistry,
    JavaScriptTreeSitterPlugin,
    PythonTreeSitterPlugin,
    TypeScriptTreeSitterPlugin,
)
from ria.resolution import (
    JavaScriptLanguageResolver,
    LanguageResolverRegistry,
    PythonLanguageResolver,
    ResolutionEngine,
    TypeScriptLanguageResolver,
)
from ria.search import (
    AutocompleteEngine,
    HighlightEngine,
    RankingEngine,
    SearchCache,
    SearchEngine,
    SearchFilterEngine,
    SearchIndex,
    SearchPlanner,
)


def test_full_search_engine_end_to_end_pipeline(tmp_path: Path) -> None:
    """End-to-End Pipeline & Performance Verification Test for C6 Search Engine:
    Git -> Sync -> Index -> Resolve -> FactStore -> SearchEngine.
    """
    # 1. Prepare git origin
    origin_dir = tmp_path / "search_origin"
    origin_dir.mkdir()
    subprocess.run(["git", "init"], cwd=origin_dir, check=True)
    subprocess.run(
        ["git", "config", "user.name", "TestRunner"], cwd=origin_dir, check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "runner@test.com"], cwd=origin_dir, check=True
    )

    py_file = origin_dir / "user_repository.py"
    py_file.write_text(
        "class UserRepository:\n    def find_by_id(self, user_id: str) -> str:\n        return 'user'\n"
    )

    subprocess.run(["git", "add", "."], cwd=origin_dir, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Search test commit"], cwd=origin_dir, check=True
    )

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

    status_dto = reg_use_case.execute(
        RegisterRepositoryCommand(remote_url=str(origin_dir), name="search_origin")
    )
    sync_dto = sync_use_case.execute(
        SynchronizeRepositoryCommand(repo_id=status_dto.repo_id)
    )
    assert sync_dto.is_success

    # 3. Index & Resolution Pipeline
    discovery = FileDiscovery(filesystem=container.filesystem)
    lang_detect = LanguageDetection(filesystem=container.filesystem)
    scanner = RepositoryScanner(
        discovery, lang_detect, container.filesystem, container.hashing
    )

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
    resolver_registry.register_resolver(
        Language.TYPESCRIPT, TypeScriptLanguageResolver()
    )
    resolver_registry.register_resolver(
        Language.JAVASCRIPT, JavaScriptLanguageResolver()
    )

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

    # 4. Setup Search Engine & Application Services
    planner = SearchPlanner()
    index = SearchIndex()
    ranking = RankingEngine()
    filters = SearchFilterEngine()
    highlight = HighlightEngine()
    autocomplete = AutocompleteEngine()
    cache = SearchCache()

    search_engine = SearchEngine(
        planner, index, ranking, filters, highlight, autocomplete, cache
    )

    search_service = SearchApplicationService(
        search_engine=search_engine,
        fact_store=fact_store,
        registry=container.repository_registry,
        clock=container.clock,
        logger=container.logger,
        metrics=container.metrics,
    )

    search_sym_uc = SearchSymbolUseCase(search_service)
    auto_uc = AutocompleteUseCase(search_service)

    # Warm-up call
    _ = search_sym_uc.execute(
        SearchSymbolDTO(
            repo_id=status_dto.repo_id, query_text="UserRepository", query_type="EXACT"
        )
    )

    # 5. Evaluate Performance & Accuracy
    # Exact Search (<5ms)
    t0 = time.perf_counter()
    exact_res = search_sym_uc.execute(
        SearchSymbolDTO(
            repo_id=status_dto.repo_id, query_text="UserRepository", query_type="EXACT"
        )
    )
    exact_lat_ms = (time.perf_counter() - t0) * 1000.0

    assert exact_res.is_success
    assert isinstance(exact_res.results.payload, tuple)
    assert len(exact_res.results.payload) == 1
    assert exact_res.results.payload[0].symbol.name == "UserRepository"
    assert exact_lat_ms < 5.0, (
        f"Exact search latency {exact_lat_ms:.2f}ms exceeded target of 5.0ms"
    )

    # Prefix Search (<10ms)
    t0 = time.perf_counter()
    prefix_res = search_sym_uc.execute(
        SearchSymbolDTO(
            repo_id=status_dto.repo_id, query_text="User", query_type="PREFIX"
        )
    )
    prefix_lat_ms = (time.perf_counter() - t0) * 1000.0

    assert prefix_res.is_success
    assert prefix_lat_ms < 10.0, (
        f"Prefix search latency {prefix_lat_ms:.2f}ms exceeded target of 10.0ms"
    )

    # Autocomplete (<5ms)
    t0 = time.perf_counter()
    auto_res = auto_uc.execute(
        AutocompleteDTO(repo_id=status_dto.repo_id, prefix="User")
    )
    auto_lat_ms = (time.perf_counter() - t0) * 1000.0

    assert auto_res.is_success
    assert isinstance(auto_res.results.payload, AutocompleteResult)
    assert len(auto_res.results.payload.suggestions) >= 1
    assert auto_lat_ms < 5.0, (
        f"Autocomplete latency {auto_lat_ms:.2f}ms exceeded target of 5.0ms"
    )
