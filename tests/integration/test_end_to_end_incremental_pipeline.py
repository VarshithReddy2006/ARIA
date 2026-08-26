"""End-to-End Integration Test for C5 Incremental Indexing Pipeline & Performance Targets."""

import subprocess
import time
from pathlib import Path

from ria.application.incremental import (
    IncrementalApplicationService,
    IncrementalUpdateCommandDTO,
    UpdateRepositoryUseCase,
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
from ria.domain.index.value_objects import Language
from ria.infrastructure.storage import SQLiteFactStoreAdapter
from ria.incremental import (
    CacheInvalidator,
    DependencyAnalyzer,
    DiffEngine,
    IncrementalEngine,
    IncrementalPlanner,
    IncrementalScheduler,
    SnapshotManager,
)
from ria.plugins import (
    PluginLoader,
    PluginRegistry,
    JavaScriptTreeSitterPlugin,
    PythonTreeSitterPlugin,
    TypeScriptTreeSitterPlugin,
)
from ria.query.cache import QueryCache
from ria.resolution import (
    JavaScriptLanguageResolver,
    LanguageResolverRegistry,
    PythonLanguageResolver,
    ResolutionEngine,
    TypeScriptLanguageResolver,
)


def test_full_incremental_indexing_end_to_end_pipeline(tmp_path: Path) -> None:
    """End-to-End Integration Test:
    Commit 1 (3 files) -> Full Sync & Index -> Commit 2 (Modify 1 file) -> Incremental Update -> Reindex ONLY 1 file.
    """
    # 1. Prepare git origin repository with 3 files
    origin_dir = tmp_path / "inc_origin"
    origin_dir.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=origin_dir, check=True)
    subprocess.run(
        ["git", "config", "user.name", "TestRunner"], cwd=origin_dir, check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "runner@test.com"], cwd=origin_dir, check=True
    )

    f1 = origin_dir / "main.py"
    f1.write_text("def run():\n    print('start')\n")

    f2 = origin_dir / "auth.py"
    f2.write_text(
        "class Authenticator:\n    def login(self) -> bool:\n        return True\n"
    )

    f3 = origin_dir / "utils.py"
    f3.write_text("def helper():\n    return 42\n")

    subprocess.run(["git", "add", "."], cwd=origin_dir, check=True)
    subprocess.run(["git", "commit", "-m", "Commit 1"], cwd=origin_dir, check=True)

    # 2. DI & Setup Application Services
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
        RegisterRepositoryCommand(remote_url=str(origin_dir), name="inc_origin")
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
    assert fact_dto.total_symbols >= 3

    # 4. Modify ONLY auth.py for Commit 2
    f2.write_text(
        "class Authenticator:\n    def login(self) -> bool:\n        return True\n    def logout(self) -> bool:\n        return True\n"
    )
    subprocess.run(["git", "add", "auth.py"], cwd=origin_dir, check=True)
    subprocess.run(["git", "commit", "-m", "Commit 2"], cwd=origin_dir, check=True)

    # 5. Setup Incremental Subsystem
    snapshot_mgr = SnapshotManager(container.clock)
    diff_engine = DiffEngine(container.git_client, container.workspace_manager)
    dep_analyzer = DependencyAnalyzer(fact_store)
    planner = IncrementalPlanner(dep_analyzer)
    cache_invalidator = CacheInvalidator()
    query_cache = QueryCache()

    scheduler = IncrementalScheduler(
        scanner=scanner,
        parser_registry=plugin_registry,
        unit_builder=builder,
        batch_assembler=assembler,
        resolution_engine=res_engine,
        fact_store=fact_store,
        workspace_manager=container.workspace_manager,
        filesystem=container.filesystem,
        cache_invalidator=cache_invalidator,
        query_cache=query_cache,
        clock=container.clock,
        logger=container.logger,
        metrics=container.metrics,
    )

    inc_engine = IncrementalEngine(snapshot_mgr, diff_engine, planner, scheduler)

    inc_app_service = IncrementalApplicationService(
        incremental_engine=inc_engine,
        registry=container.repository_registry,
        git_client=container.git_client,
        workspace_manager=container.workspace_manager,
        clock=container.clock,
        logger=container.logger,
        metrics=container.metrics,
    )
    update_use_case = UpdateRepositoryUseCase(inc_app_service)

    # 6. Execute Incremental Update & Measure Performance
    t0 = time.perf_counter()
    inc_dto = update_use_case.execute(
        IncrementalUpdateCommandDTO(repo_id=status_dto.repo_id)
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    # 7. Assertions
    assert inc_dto.is_success
    assert inc_dto.files_reindexed == 1  # Reindexed ONLY 1 changed file!
    assert inc_dto.files_deleted == 0
    assert elapsed_ms < 2500.0  # Incremental update fast target

    # 8. Assert updated symbols in FactStore
    all_states = container.repository_registry.list_all()
    repo_state = next(
        st for st in all_states if st.identity.repo_id.value == status_dto.repo_id
    )
    assert repo_state.current_commit is not None

    stored_symbols = fact_store.get_symbols(
        repo_state.identity, repo_state.current_commit
    )
    stored_names = {sym.name for sym in stored_symbols}
    assert "logout" in stored_names
