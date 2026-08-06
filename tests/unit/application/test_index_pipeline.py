"""Unit tests for Index Core Application components and IndexPipeline."""

from pathlib import Path

import pytest
from ria.application.index import (
    ExecutePipelineCommand,
    FileDiscovery,
    IndexBatchAssembler,
    IndexPipeline,
    IndexUnitBuilder,
    LanguageDetection,
    PipelineException,
    RepositoryScanner,
)
from ria.domain.common.value_objects import Timestamp, UUIDv4
from ria.domain.index.value_objects import FilePath, Language
from ria.domain.sync import (
    BranchReference,
    CommitReference,
    RepositoryIdentity,
    RepositoryMetadata,
    RepositoryState,
    SyncStatus,
)
from ria.infrastructure.filesystem import OSFilesystemAdapter, WorkspaceManager
from ria.infrastructure.storage import SQLiteRepositoryRegistryAdapter
from ria.infrastructure.system import (
    HashlibHashingAdapter,
    InMemoryMetricsAdapter,
    StandardLoggerAdapter,
    SystemClockAdapter,
)
from ria.plugins import (
    PluginLoader,
    PluginRegistry,
    PythonTreeSitterPlugin,
    TypeScriptTreeSitterPlugin,
)


def test_file_discovery_and_language_detection(tmp_path: Path) -> None:
    fs = OSFilesystemAdapter()
    discovery = FileDiscovery(filesystem=fs, max_file_size_bytes=100)
    lang_detect = LanguageDetection(filesystem=fs)

    py_file = tmp_path / "app.py"
    py_file.write_text("print('hello')")

    ts_file = tmp_path / "index.ts"
    ts_file.write_text("const x = 1;")

    # Binary file
    bin_file = tmp_path / "image.png"
    bin_file.write_bytes(b"\x89PNG\r\n\x1a\n")

    # Oversized file
    big_file = tmp_path / "big.txt"
    big_file.write_text("a" * 200)

    # Shebang file without extension
    sh_file = tmp_path / "script_py"
    sh_file.write_text("#!/usr/bin/env python3\nprint('shebang')")

    sh_js = tmp_path / "script_js"
    sh_js.write_text("#!/usr/bin/env node\nconsole.log('node')")

    discovered = discovery.discover_files(tmp_path)
    disc_names = {fp.relative_path for fp in discovered}

    assert "app.py" in disc_names
    assert "index.ts" in disc_names
    assert "image.png" not in disc_names
    assert "big.txt" not in disc_names
    assert "script_py" in disc_names

    assert (
        lang_detect.detect_language(sh_file, FilePath(relative_path="script_py"))
        == Language.PYTHON
    )
    assert (
        lang_detect.detect_language(sh_js, FilePath(relative_path="script_js"))
        == Language.JAVASCRIPT
    )


def test_index_pipeline_execution(tmp_path: Path) -> None:
    ws_dir = tmp_path / "workspaces" / "repo_5ac37926-9cf1-438b-ad3d-b4786ad584e1"
    ws_dir.mkdir(parents=True)

    py_file = ws_dir / "calculator.py"
    py_file.write_text("def multiply(a: int, b: int) -> int:\n    return a * b\n")

    fs = OSFilesystemAdapter()
    hashing = HashlibHashingAdapter()
    clock = SystemClockAdapter()
    logger = StandardLoggerAdapter("test")
    metrics = InMemoryMetricsAdapter()

    discovery = FileDiscovery(filesystem=fs)
    lang_detect = LanguageDetection(filesystem=fs)
    scanner = RepositoryScanner(discovery, lang_detect, fs, hashing)

    plugin_registry = PluginRegistry()
    loader = PluginLoader(plugin_registry)
    loader.load_plugin_class(PythonTreeSitterPlugin)
    loader.load_plugin_class(TypeScriptTreeSitterPlugin)

    builder = IndexUnitBuilder()
    assembler = IndexBatchAssembler()
    db_registry = SQLiteRepositoryRegistryAdapter(db_path=":memory:")
    workspace_mgr = WorkspaceManager(base_dir=tmp_path / "workspaces")

    repo_id_val = "5ac37926-9cf1-438b-ad3d-b4786ad584e1"
    repo_identity = RepositoryIdentity(
        repo_id=UUIDv4(value=repo_id_val),
        remote_url="https://github.com/org/repo.git",
        name="repo",
    )
    commit = CommitReference(sha="f" * 40, committed_at=Timestamp.now())
    branch = BranchReference(name="main", head_commit=commit)
    metadata = RepositoryMetadata(
        file_count=1,
        total_bytes=100,
        default_branch="main",
        registered_at=Timestamp.now(),
    )

    state = RepositoryState(
        identity=repo_identity, status=SyncStatus.UNINITIALIZED, metadata=metadata
    )
    state.mark_synchronized(branch=branch, commit=commit, synced_at=Timestamp.now())
    db_registry.save_state(state)

    pipeline = IndexPipeline(
        scanner=scanner,
        parser_registry=plugin_registry,
        unit_builder=builder,
        batch_assembler=assembler,
        registry=db_registry,
        workspace_manager=workspace_mgr,
        filesystem=fs,
        clock=clock,
        logger=logger,
        metrics=metrics,
    )

    # Test incremental scan
    inc_units = scanner.scan_incremental(
        ws_dir, [FilePath(relative_path="calculator.py")]
    )
    assert len(inc_units) == 1

    cmd = ExecutePipelineCommand(repo_id=repo_id_val)
    batch, dto = pipeline.execute(cmd)

    assert dto.is_success
    assert dto.total_files_discovered == 1
    assert dto.total_files_parsed == 1
    assert len(batch.parse_units) == 1
    assert batch.parse_units[0].ast_unit is not None
    assert batch.parse_units[0].ast_unit.root_node.type == "module"


def test_index_pipeline_errors(tmp_path: Path) -> None:
    fs = OSFilesystemAdapter()
    hashing = HashlibHashingAdapter()
    clock = SystemClockAdapter()
    logger = StandardLoggerAdapter("test")
    metrics = InMemoryMetricsAdapter()

    discovery = FileDiscovery(filesystem=fs)
    lang_detect = LanguageDetection(filesystem=fs)
    scanner = RepositoryScanner(discovery, lang_detect, fs, hashing)

    plugin_registry = PluginRegistry()
    builder = IndexUnitBuilder()
    assembler = IndexBatchAssembler()
    db_registry = SQLiteRepositoryRegistryAdapter(db_path=":memory:")
    workspace_mgr = WorkspaceManager(base_dir=tmp_path / "workspaces")

    pipeline = IndexPipeline(
        scanner=scanner,
        parser_registry=plugin_registry,
        unit_builder=builder,
        batch_assembler=assembler,
        registry=db_registry,
        workspace_manager=workspace_mgr,
        filesystem=fs,
        clock=clock,
        logger=logger,
        metrics=metrics,
    )

    dummy_uuid = UUIDv4.generate().value
    with pytest.raises(PipelineException, match="not registered"):
        pipeline.execute(ExecutePipelineCommand(repo_id=dummy_uuid))
