"""Unit tests for RepositorySyncService."""

from pathlib import Path

import pytest
from ria.application.sync import (
    RegisterRepositoryCommand,
    RepositorySyncException,
    RepositorySyncService,
    SynchronizeRepositoryCommand,
)
from ria.domain.common.value_objects import UUIDv4
from ria.domain.sync import SyncStatus
from ria.infrastructure.filesystem import WorkspaceManager
from ria.infrastructure.git import SubprocessGitAdapter
from ria.infrastructure.storage import (
    SQLiteRepositoryLockAdapter,
    SQLiteRepositoryRegistryAdapter,
)
from ria.infrastructure.system import (
    InMemoryMetricsAdapter,
    StandardLoggerAdapter,
    SystemClockAdapter,
)


def test_register_and_sync_repository_flow(tmp_path: Path) -> None:
    import subprocess

    # Create dummy origin git repo
    origin_dir = tmp_path / "origin"
    origin_dir.mkdir()
    subprocess.run(["git", "init"], cwd=origin_dir, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=origin_dir, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"], cwd=origin_dir, check=True
    )

    f1 = origin_dir / "main.py"
    f1.write_text("print('hello')")
    subprocess.run(["git", "add", "main.py"], cwd=origin_dir, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"], cwd=origin_dir, check=True
    )

    git_client = SubprocessGitAdapter(timeout_seconds=10.0)
    registry = SQLiteRepositoryRegistryAdapter(db_path=":memory:")
    lock_mgr = SQLiteRepositoryLockAdapter(db_path=":memory:")
    workspace_mgr = WorkspaceManager(base_dir=tmp_path / "workspaces")
    clock = SystemClockAdapter()
    logger = StandardLoggerAdapter("test")
    metrics = InMemoryMetricsAdapter()

    service = RepositorySyncService(
        git_client=git_client,
        registry=registry,
        lock_manager=lock_mgr,
        workspace_manager=workspace_mgr,
        clock=clock,
        logger=logger,
        metrics=metrics,
    )

    # 1. Register
    reg_cmd = RegisterRepositoryCommand(
        remote_url=str(origin_dir),
        name="test_repo",
        default_branch="main",
    )
    status_dto = service.register_repository(reg_cmd)
    assert status_dto.status == SyncStatus.UNINITIALIZED.value

    # 2. Sync
    sync_cmd = SynchronizeRepositoryCommand(repo_id=status_dto.repo_id)
    result_dto = service.synchronize_repository(sync_cmd)

    assert result_dto.is_success
    assert result_dto.status == SyncStatus.SYNCHRONIZED.value
    assert len(result_dto.current_commit_sha) == 40


def test_synchronize_unregistered_repository() -> None:
    git_client = SubprocessGitAdapter(timeout_seconds=10.0)
    registry = SQLiteRepositoryRegistryAdapter(db_path=":memory:")
    lock_mgr = SQLiteRepositoryLockAdapter(db_path=":memory:")
    workspace_mgr = WorkspaceManager(base_dir=Path("/tmp/workspaces"))
    clock = SystemClockAdapter()
    logger = StandardLoggerAdapter("test")
    metrics = InMemoryMetricsAdapter()

    service = RepositorySyncService(
        git_client=git_client,
        registry=registry,
        lock_manager=lock_mgr,
        workspace_manager=workspace_mgr,
        clock=clock,
        logger=logger,
        metrics=metrics,
    )

    dummy_id = UUIDv4.generate().value
    with pytest.raises(RepositorySyncException, match="not registered"):
        service.synchronize_repository(SynchronizeRepositoryCommand(repo_id=dummy_id))
