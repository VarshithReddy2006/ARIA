"""Integration tests for Milestone 6 — Repository Digital Twin (Phase 15)."""

from __future__ import annotations

from datetime import datetime, timezone
import pytest

from ria.application.twin_service import RepositoryTwinService
from ria.domain.enums import TwinState
from ria.domain.identity import CommitSha, Moniker, RepositoryId
from ria.domain.models.graph import Graph
from ria.domain.models.graph_identity import GraphFingerprint
from ria.domain.models.graph_result import GraphMetadata, GraphStatistics
from ria.domain.models.graph_snapshot import GraphSnapshot
from ria.domain.models.repository import Repository
from ria.infrastructure.storage.sqlite.connection import ConnectionProvider
from ria.infrastructure.storage.sqlite.migrations import MigrationRunner
from ria.infrastructure.storage.sqlite.twin_store import (
    SqliteTwinCacheStore,
    SqliteTwinStore,
)


@pytest.fixture
def twin_db() -> ConnectionProvider:
    provider = ConnectionProvider(":memory:")
    runner = MigrationRunner(provider)
    runner.run()
    return provider


def test_repository_wide_twin_integration(twin_db: ConnectionProvider) -> None:
    store = SqliteTwinStore(twin_db)
    cache = SqliteTwinCacheStore(twin_db)

    svc = RepositoryTwinService(store=store, cache_store=cache)
    repo_id = RepositoryId("twin-repo")
    sha1 = CommitSha("1" * 40)
    now = datetime.now(timezone.utc)

    repo = Repository(
        repository_id=repo_id,
        moniker=Moniker.parse("repo:github.com:org/twin-repo"),
        origin_url="https://github.com/org/twin-repo.git",
        default_branch="main",
        tenant_id="default",
        registered_at=now,
        updated_at=now,
    )

    g_fp = GraphFingerprint("builder", "1.0.0")
    g_snap1 = GraphSnapshot(
        repo_id,
        sha1,
        Graph(),
        g_fp,
        GraphMetadata("twin-repo", sha1.value),
        GraphStatistics(),
    )

    # 1. Build Twin
    twin1 = svc.build_twin(repo, sha1, g_snap1)
    assert twin1.repository.repository_id == repo_id
    assert twin1.state.current_commit_sha == sha1

    # 2. Save & Load Snapshot
    snap1 = svc.create_snapshot(twin1)
    loaded_snap = svc.load_snapshot(repo_id, sha1)
    assert loaded_snap is not None
    assert loaded_snap.twin_id == snap1.twin_id

    # 3. Synchronize
    sync_res = svc.synchronize(repo_id, sha1)
    assert sync_res.state is TwinState.SYNCHRONIZED

    # 4. Metrics & Consistency
    metrics = svc.compute_metrics(twin1)
    assert metrics.cyclomatic_complexity_average >= 1.0

    report = svc.validate_consistency(twin1)
    assert report.is_consistent
