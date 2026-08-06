"""End-to-End Integration Test for C3 Fact Store Pipeline."""

import subprocess
from pathlib import Path

from ria.application.index import (
    FileDiscovery,
    IndexBatchAssembler,
    IndexPipeline,
    IndexUnitBuilder,
    LanguageDetection,
    RepositoryScanner,
)
from ria.application.resolution import ResolveAndStoreCommand, ResolveAndStoreUseCase, ResolutionApplicationService
from ria.application.sync import (
    RegisterRepositoryCommand,
    RegisterRepositoryUseCase,
    SynchronizeRepositoryCommand,
    SynchronizeRepositoryUseCase,
)
from ria.config import Container, Settings
from ria.domain.index.value_objects import FilePath, Language
from ria.infrastructure.storage import SQLiteFactStoreAdapter
from ria.plugins import PluginLoader, PluginRegistry, JavaScriptTreeSitterPlugin, PythonTreeSitterPlugin, TypeScriptTreeSitterPlugin
from ria.resolution import (
    JavaScriptLanguageResolver,
    LanguageResolverRegistry,
    PythonLanguageResolver,
    ResolutionEngine,
    TypeScriptLanguageResolver,
)


def test_full_fact_store_end_to_end_pipeline(tmp_path: Path) -> None:
    """End-to-End Pipeline Test:
    Git -> Sync -> Index Core -> Resolution Engine -> SQLite FactStore Persistence -> Fact Querying.
    """
    # 1. Prepare git origin
    origin_dir = tmp_path / "fact_origin"
    origin_dir.mkdir()
    subprocess.run(["git", "init"], cwd=origin_dir, check=True)
    subprocess.run(["git", "config", "user.name", "TestRunner"], cwd=origin_dir, check=True)
    subprocess.run(["git", "config", "user.email", "runner@test.com"], cwd=origin_dir, check=True)

    py_file = origin_dir / "server.py"
    py_file.write_text("class HttpServer:\n    def listen(self, port: int) -> None:\n        pass\n")

    subprocess.run(["git", "add", "."], cwd=origin_dir, check=True)
    subprocess.run(["git", "commit", "-m", "Fact store test commit"], cwd=origin_dir, check=True)

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

    status_dto = reg_use_case.execute(RegisterRepositoryCommand(remote_url=str(origin_dir), name="fact_origin"))
    sync_dto = sync_use_case.execute(SynchronizeRepositoryCommand(repo_id=status_dto.repo_id))
    assert sync_dto.is_success

    # 3. Setup Index Pipeline
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

    # 4. Setup Resolution Engine & FactStore Adapter
    resolver_registry = LanguageResolverRegistry()
    resolver_registry.register_resolver(Language.PYTHON, PythonLanguageResolver())
    resolver_registry.register_resolver(Language.TYPESCRIPT, TypeScriptLanguageResolver())
    resolver_registry.register_resolver(Language.JAVASCRIPT, JavaScriptLanguageResolver())

    engine = ResolutionEngine(resolver_registry=resolver_registry)
    fact_store = SQLiteFactStoreAdapter(db_path=tmp_path / "fact_store.db")

    res_service = ResolutionApplicationService(
        index_pipeline=pipeline,
        resolution_engine=engine,
        fact_store=fact_store,
        registry=container.repository_registry,
        clock=container.clock,
        logger=container.logger,
        metrics=container.metrics,
    )
    res_use_case = ResolveAndStoreUseCase(res_service)

    # 5. Execute Resolve and Store
    fact_dto = res_use_case.execute(ResolveAndStoreCommand(repo_id=status_dto.repo_id))

    assert fact_dto.is_success
    assert fact_dto.total_symbols >= 2
    assert fact_dto.total_definitions >= 2

    # 6. Verify Persistence & Relational Querying from SQLite FactStore
    all_states = container.repository_registry.list_all()
    repo_state = next(st for st in all_states if st.identity.repo_id.value == status_dto.repo_id)

    assert repo_state.current_commit is not None
    stored_symbols = fact_store.get_symbols(repo_state.identity, repo_state.current_commit)
    assert len(stored_symbols) >= 2

    stored_names = {sym.name for sym in stored_symbols}
    assert "HttpServer" in stored_names
    assert "listen" in stored_names

    # Filter query
    server_file_symbols = fact_store.get_symbols(
        repo_state.identity,
        repo_state.current_commit,
        path=FilePath(relative_path="server.py"),
    )
    assert len(server_file_symbols) >= 2
