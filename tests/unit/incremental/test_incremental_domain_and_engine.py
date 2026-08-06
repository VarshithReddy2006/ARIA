"""Unit tests for C5 Incremental Indexing domain models, components, and engine."""

from pathlib import Path

import pytest
from ria.domain.common.value_objects import Timestamp, UUIDv4
from ria.domain.index.value_objects import FilePath
from ria.domain.snapshot import (
    CacheInvalidationPlan,
    ChangedFile,
    ChangedFileType,
    DependencyImpact,
    IncrementalPlan,
    InvalidSnapshotError,
    RepositorySnapshot,
    RepositorySnapshotId,
    SnapshotMetadata,
)
from ria.domain.sync import BranchReference, CommitReference, RepositoryIdentity
from ria.incremental import (
    CacheInvalidator,
    DependencyAnalyzer,
    DiffEngine,
    IncrementalEngine,
    IncrementalPlanner,
    SnapshotManager,
)
from ria.infrastructure.storage import SQLiteFactStoreAdapter
from ria.infrastructure.system import StandardLoggerAdapter, SystemClockAdapter
from ria.query.cache import QueryCache


def test_snapshot_domain_value_objects() -> None:
    snap_id = RepositorySnapshotId(value="snap_123")
    assert snap_id.value == "snap_123"

    with pytest.raises(InvalidSnapshotError):
        RepositorySnapshotId(value="")


def test_snapshot_manager_and_cache_invalidator() -> None:
    clock = SystemClockAdapter()
    mgr = SnapshotManager(clock)

    repo_id = RepositoryIdentity(repo_id=UUIDv4.generate(), remote_url="https://github.com/org/repo.git", name="repo")
    commit = CommitReference(sha="a" * 40, committed_at=Timestamp.now())

    snapshot = mgr.create_snapshot(repo_id, commit, total_files=10, total_symbols=50)
    assert snapshot.metadata.total_files == 10

    latest = mgr.get_latest_snapshot(repo_id)
    assert latest is not None
    assert latest.commit == commit

    # Cache Invalidator
    invalidator = CacheInvalidator()
    cache = QueryCache()
    plan = IncrementalPlan(
        repo_id=repo_id,
        from_commit=commit,
        to_commit=commit,
        files_to_reindex=(FilePath(relative_path="main.py"),),
    )

    inv_plan = invalidator.invalidate(cache, plan)
    assert "partition_cleared" in inv_plan.invalidated_queries


def test_dependency_analyzer_and_planner() -> None:
    fact_store = SQLiteFactStoreAdapter(db_path=":memory:")
    analyzer = DependencyAnalyzer(fact_store)
    planner = IncrementalPlanner(analyzer)

    repo_id = RepositoryIdentity(repo_id=UUIDv4.generate(), remote_url="https://github.com/org/repo.git", name="repo")
    c1 = CommitReference(sha="b" * 40, committed_at=Timestamp.now())
    c2 = CommitReference(sha="c" * 40, committed_at=Timestamp.now())

    clock = SystemClockAdapter()
    mgr = SnapshotManager(clock)
    snapshot = mgr.create_snapshot(repo_id, c1, total_files=5, total_symbols=20)

    cf = ChangedFile(path=FilePath(relative_path="auth.py"), change_type=ChangedFileType.MODIFIED)
    plan = planner.build_plan(snapshot, c2, (cf,))

    assert plan.from_commit == c1
    assert plan.to_commit == c2
    assert FilePath(relative_path="auth.py") in plan.files_to_reindex
