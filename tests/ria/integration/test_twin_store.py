"""Integration tests for SqliteTwinStore and SqliteTwinCacheStore (Phase 8)."""

from __future__ import annotations

from datetime import datetime, timezone
import pytest

from ria.application.twin_builder import TwinBuilderService
from ria.domain.identity import CommitSha, Moniker, RepositoryId
from ria.domain.models.graph import Graph
from ria.domain.models.graph_identity import GraphFingerprint
from ria.domain.models.graph_result import GraphMetadata, GraphStatistics
from ria.domain.models.graph_snapshot import GraphSnapshot
from ria.domain.models.repository import Repository
from ria.domain.models.twin_identity import TwinCacheKey, TwinFingerprint
from ria.domain.models.twin_snapshot import TwinSnapshot
from ria.infrastructure.storage.sqlite.connection import ConnectionProvider
from ria.infrastructure.storage.sqlite.migrations import MigrationRunner
from ria.infrastructure.storage.sqlite.twin_store import (
    SqliteTwinCacheStore,
    SqliteTwinStore,
)


@pytest.fixture
def memory_db() -> ConnectionProvider:
    provider = ConnectionProvider(":memory:")
    runner = MigrationRunner(provider)
    runner.run()
    return provider


def test_sqlite_twin_store_and_cache(memory_db: ConnectionProvider) -> None:
    store = SqliteTwinStore(memory_db)
    cache = SqliteTwinCacheStore(memory_db)

    repo_id = RepositoryId("repo1")
    sha = CommitSha("a" * 40)
    now = datetime.now(timezone.utc)

    repo = Repository(
        repository_id=repo_id,
        moniker=Moniker.parse("repo:github.com:org/repo1"),
        origin_url="https://github.com/org/repo1.git",
        default_branch="main",
        tenant_id="default",
        registered_at=now,
        updated_at=now,
    )

    g_fp = GraphFingerprint("builder", "1.0.0")
    g_snap = GraphSnapshot(
        repo_id,
        sha,
        Graph(),
        g_fp,
        GraphMetadata("repo1", sha.value),
        GraphStatistics(),
    )

    builder = TwinBuilderService()
    twin = builder.build_twin(repo, sha, g_snap)

    t_fp = TwinFingerprint("twin-builder")
    snap = TwinSnapshot(
        twin_id=twin.twin_id,
        repository_id=repo_id,
        commit_sha=sha,
        twin=twin,
        fingerprint=t_fp,
    )

    # Test Store
    store.save_snapshot(snap)
    loaded = store.get_snapshot(repo_id, sha)
    assert loaded is not None
    assert loaded.twin_id == twin.twin_id

    # Test Cache
    key = TwinCacheKey(repository_id=repo_id, commit_sha=sha, fingerprint=t_fp)
    cache.put(key, snap)
    cached = cache.get(key)
    assert cached is not None
    assert cached.twin_id == twin.twin_id
