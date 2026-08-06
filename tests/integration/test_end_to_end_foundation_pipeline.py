"""End-to-End Integration Test for Foundation Iteration 1 (C0 Sync & C1 Index Core)."""

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
from ria.plugins import PluginLoader, PluginRegistry, PythonTreeSitterPlugin, TypeScriptTreeSitterPlugin


def test_full_foundation_iteration_1_pipeline(tmp_path: Path) -> None:
    """Full End-to-End Integration Test:
    Git URL -> Clone -> Synchronize -> Discover Files -> Language Detection -> Select Tree-sitter Plugin -> Parse -> Emit IndexBatch.
    """
    # 1. Prepare origin git repository fixture
    origin_dir = tmp_path / "sample_origin"
    origin_dir.mkdir()
    subprocess.run(["git", "init"], cwd=origin_dir, check=True)
    subprocess.run(["git", "config", "user.name", "TestRunner"], cwd=origin_dir, check=True)
    subprocess.run(["git", "config", "user.email", "runner@test.com"], cwd=origin_dir, check=True)

    py_file = origin_dir / "service.py"
    py_file.write_text("class AuthManager:\n    def login(self, username: str) -> bool:\n        return True\n")

    ts_file = origin_dir / "models.ts"
    ts_file.write_text("export interface UserProfile {\n  id: string;\n  email: string;\n}\n")

    subprocess.run(["git", "add", "."], cwd=origin_dir, check=True)
    subprocess.run(["git", "commit", "-m", "Initial foundation commit"], cwd=origin_dir, check=True)

    # 2. Wire DI Container
    settings = Settings.create_testing(tmp_path)
    container = Container.create(settings)

    # 3. Setup application services & Use Cases
    reg_use_case = RegisterRepositoryUseCase(container.repository_registry_service if hasattr(container, "repository_registry_service") else None)  # type: ignore
    # Instantiate Sync Service
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

    # 4. Step 1: Register
    reg_cmd = RegisterRepositoryCommand(remote_url=str(origin_dir), name="sample_origin", default_branch="main")
    status_dto = reg_use_case.execute(reg_cmd)
    repo_id = status_dto.repo_id

    # 5. Step 2: Synchronize
    sync_cmd = SynchronizeRepositoryCommand(repo_id=repo_id)
    sync_dto = sync_use_case.execute(sync_cmd)
    assert sync_dto.is_success
    assert len(sync_dto.current_commit_sha) == 40

    # 6. Setup Index Core & Pipeline
    discovery = FileDiscovery(filesystem=container.filesystem, max_file_size_bytes=settings.max_file_size_bytes)
    lang_detect = LanguageDetection(filesystem=container.filesystem)
    scanner = RepositoryScanner(discovery, lang_detect, container.filesystem, container.hashing)

    plugin_registry = PluginRegistry()
    loader = PluginLoader(plugin_registry)
    loader.load_plugin_class(PythonTreeSitterPlugin)
    loader.load_plugin_class(TypeScriptTreeSitterPlugin)

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

    # 7. Step 3: Execute Index Pipeline
    pipe_cmd = ExecutePipelineCommand(repo_id=repo_id)
    index_batch, pipe_dto = pipeline.execute(pipe_cmd)

    # 8. Assertions
    assert pipe_dto.is_success
    assert pipe_dto.total_files_discovered == 2
    assert pipe_dto.total_files_parsed == 2
    assert pipe_dto.total_files_failed == 0
    assert len(index_batch.parse_units) == 2

    # Verify ASTUnits
    parsed_files = {pu.file_unit.path.relative_path: pu for pu in index_batch.parse_units}
    assert "service.py" in parsed_files
    assert "models.ts" in parsed_files

    assert parsed_files["service.py"].ast_unit is not None
    assert parsed_files["service.py"].ast_unit.root_node.type == "module"
    assert parsed_files["models.ts"].ast_unit is not None
    assert parsed_files["models.ts"].ast_unit.root_node.type == "program"
