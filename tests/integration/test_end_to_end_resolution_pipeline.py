"""End-to-End Integration Test for C2 Semantic Resolution Engine."""

import subprocess
from pathlib import Path

from ria.application.index import (
    ExecutePipelineCommand,
    FileDiscovery,
    IndexBatchAssembler,
    IndexPipeline,
    IndexUnitBuilder,
    LanguageDetection,
    RepositoryScanner,
)
from ria.application.sync import (
    RegisterRepositoryCommand,
    RegisterRepositoryUseCase,
    SynchronizeRepositoryCommand,
    SynchronizeRepositoryUseCase,
)
from ria.config import Container, Settings
from ria.domain.index.value_objects import Language
from ria.plugins import PluginLoader, PluginRegistry, JavaScriptTreeSitterPlugin, PythonTreeSitterPlugin, TypeScriptTreeSitterPlugin
from ria.resolution import (
    JavaScriptLanguageResolver,
    LanguageResolverRegistry,
    PythonLanguageResolver,
    ResolutionEngine,
    TypeScriptLanguageResolver,
)


def test_full_semantic_resolution_pipeline(tmp_path: Path) -> None:
    """Full Integration Test: Git Origin -> Clone -> Sync -> Index Core -> Resolution Engine -> ResolvedFactSet."""
    # 1. Prepare git origin
    origin_dir = tmp_path / "resolution_origin"
    origin_dir.mkdir()
    subprocess.run(["git", "init"], cwd=origin_dir, check=True)
    subprocess.run(["git", "config", "user.name", "TestRunner"], cwd=origin_dir, check=True)
    subprocess.run(["git", "config", "user.email", "runner@test.com"], cwd=origin_dir, check=True)

    py_file = origin_dir / "auth.py"
    py_file.write_text("class Authenticator:\n    def validate(self, token: str) -> bool:\n        return True\n")

    ts_file = origin_dir / "app.ts"
    ts_file.write_text("import { Authenticator } from './auth';\nfunction main() {\n  console.log('running');\n}\n")

    subprocess.run(["git", "add", "."], cwd=origin_dir, check=True)
    subprocess.run(["git", "commit", "-m", "Resolution test commit"], cwd=origin_dir, check=True)

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

    status_dto = reg_use_case.execute(RegisterRepositoryCommand(remote_url=str(origin_dir), name="resolution_origin"))
    sync_dto = sync_use_case.execute(SynchronizeRepositoryCommand(repo_id=status_dto.repo_id))
    assert sync_dto.is_success

    # 3. Execute IndexPipeline
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

    index_batch, pipe_dto = pipeline.execute(ExecutePipelineCommand(repo_id=status_dto.repo_id))
    assert pipe_dto.is_success
    assert len(index_batch.parse_units) == 2

    # 4. Execute ResolutionEngine
    resolver_registry = LanguageResolverRegistry()
    resolver_registry.register_resolver(Language.PYTHON, PythonLanguageResolver())
    resolver_registry.register_resolver(Language.TYPESCRIPT, TypeScriptLanguageResolver())
    resolver_registry.register_resolver(Language.JAVASCRIPT, JavaScriptLanguageResolver())

    engine = ResolutionEngine(resolver_registry=resolver_registry)
    fact_set = engine.resolve_batch(index_batch)

    # 5. Assertions on ResolvedFactSet
    assert len(fact_set.symbols) >= 3  # Class Authenticator, validate method, main function
    assert len(fact_set.definitions) >= 3
    assert fact_set.total_facts > 0

    names = {s.name for s in fact_set.symbols}
    assert "Authenticator" in names
    assert "validate" in names
    assert "main" in names
