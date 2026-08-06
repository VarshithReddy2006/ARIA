"""End-to-End Integration Test for C7 Context Builder Pipeline & Performance Targets."""

import subprocess
import time
from pathlib import Path

from ria.application.context import (
    BuildContextCommandDTO,
    BuildContextUseCase,
    ContextApplicationService,
)
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
from ria.application.sync import (
    RegisterRepositoryCommand,
    RegisterRepositoryUseCase,
    SynchronizeRepositoryCommand,
    SynchronizeRepositoryUseCase,
)
from ria.config import Container, Settings
from ria.context import (
    CallExpander,
    ContextBuilder,
    ContextEngine,
    ContextExpander,
    ContextSerializer,
    Deduplicator,
    DependencyExpander,
    RankingEngine,
    ReferenceExpander,
    TokenBudgetOptimizer,
)
from ria.domain.index.value_objects import Language
from ria.infrastructure.storage import SQLiteFactStoreAdapter
from ria.plugins import (
    PluginLoader,
    PluginRegistry,
    JavaScriptTreeSitterPlugin,
    PythonTreeSitterPlugin,
    TypeScriptTreeSitterPlugin,
)
from ria.query import (
    QueryCache,
    QueryEngine,
    QueryExecutor,
    QueryOptimizer,
    QueryPlanner,
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
    RankingEngine as SearchRankingEngine,
    SearchCache,
    SearchEngine,
    SearchFilterEngine,
    SearchIndex,
    SearchPlanner,
)


def test_full_context_builder_end_to_end_pipeline(tmp_path: Path) -> None:
    """End-to-End Pipeline & Performance Verification Test for C7 Context Builder:
    Git -> Sync -> Index -> Resolve -> FactStore -> SearchEngine -> QueryEngine -> ContextBuilder.
    """
    # 1. Prepare git origin
    origin_dir = tmp_path / "ctx_origin"
    origin_dir.mkdir()
    subprocess.run(["git", "init"], cwd=origin_dir, check=True)
    subprocess.run(
        ["git", "config", "user.name", "TestRunner"], cwd=origin_dir, check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "runner@test.com"], cwd=origin_dir, check=True
    )

    py_file = origin_dir / "user_service.py"
    py_file.write_text(
        "class UserService:\n    def get_user(self, user_id: str) -> str:\n        return 'user'\n"
    )

    subprocess.run(["git", "add", "."], cwd=origin_dir, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Context test commit"], cwd=origin_dir, check=True
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
        RegisterRepositoryCommand(remote_url=str(origin_dir), name="ctx_origin")
    )
    sync_dto = sync_use_case.execute(
        SynchronizeRepositoryCommand(repo_id=status_dto.repo_id)
    )
    assert sync_dto.is_success

    # 3. Setup Index & Resolution Pipelines
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

    # 4. Setup Search & Query Engines
    search_planner = SearchPlanner()
    search_index = SearchIndex()
    search_ranking = SearchRankingEngine()
    search_filters = SearchFilterEngine()
    search_hl = HighlightEngine()
    search_auto = AutocompleteEngine()
    search_cache = SearchCache()
    search_engine = SearchEngine(
        search_planner,
        search_index,
        search_ranking,
        search_filters,
        search_hl,
        search_auto,
        search_cache,
    )

    q_planner = QueryPlanner()
    q_executor = QueryExecutor()
    q_optimizer = QueryOptimizer()
    q_cache = QueryCache()
    query_engine = QueryEngine(q_planner, q_executor, q_optimizer, q_cache)

    # 5. Setup Context Builder Engine
    ref_exp = ReferenceExpander()
    call_exp = CallExpander()
    dep_exp = DependencyExpander()
    expander = ContextExpander(ref_exp, call_exp, dep_exp)
    ranker = RankingEngine()
    deduplicator = Deduplicator()
    budget_optimizer = TokenBudgetOptimizer()

    context_builder = ContextBuilder(expander, ranker, deduplicator, budget_optimizer)
    serializer = ContextSerializer()
    context_engine = ContextEngine(context_builder, serializer)

    context_service = ContextApplicationService(
        context_engine=context_engine,
        search_engine=search_engine,
        query_engine=query_engine,
        fact_store=fact_store,
        registry=container.repository_registry,
        clock=container.clock,
        logger=container.logger,
        metrics=container.metrics,
    )

    build_ctx_uc = BuildContextUseCase(context_service)

    # 6. Evaluate Performance & Accuracy
    # Warm up call
    _ = build_ctx_uc.execute(
        BuildContextCommandDTO(
            repo_id=status_dto.repo_id, question="UserService", max_tokens=4000
        )
    )

    t0 = time.perf_counter()
    resp_dto = build_ctx_uc.execute(
        BuildContextCommandDTO(
            repo_id=status_dto.repo_id,
            question="UserService",
            max_tokens=4000,
            format="json",
        )
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert resp_dto.is_success
    assert resp_dto.total_snippets >= 1
    assert resp_dto.total_tokens <= 4000
    assert "UserService" in resp_dto.content
    assert elapsed_ms < 30.0, (
        f"Context assembly latency {elapsed_ms:.2f}ms exceeded target of 30.0ms"
    )
