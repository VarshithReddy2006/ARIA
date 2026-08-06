"""Unit tests for TwinSnapshotManager (Phase 5)."""

from __future__ import annotations

from datetime import datetime, timezone

from ria.application.twin_builder import TwinBuilderService
from ria.application.twin_snapshot_manager import TwinSnapshotManager
from ria.domain.identity import CommitSha, Moniker, RepositoryId
from ria.domain.models.graph import Graph
from ria.domain.models.graph_identity import GraphFingerprint
from ria.domain.models.graph_result import GraphMetadata, GraphStatistics
from ria.domain.models.graph_snapshot import GraphSnapshot
from ria.domain.models.repository import Repository


def test_snapshot_manager_create_and_compare() -> None:
    repo_id = RepositoryId("repo1")
    sha1 = CommitSha("1" * 40)
    sha2 = CommitSha("2" * 40)
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
    g_snap1 = GraphSnapshot(
        repo_id,
        sha1,
        Graph(),
        g_fp,
        GraphMetadata("repo1", sha1.value),
        GraphStatistics(),
    )
    g_snap2 = GraphSnapshot(
        repo_id,
        sha2,
        Graph(),
        g_fp,
        GraphMetadata("repo1", sha2.value),
        GraphStatistics(),
    )

    builder = TwinBuilderService()
    twin1 = builder.build_twin(repo, sha1, g_snap1)
    twin2 = builder.build_twin(repo, sha2, g_snap2)

    mgr = TwinSnapshotManager()
    snap1 = mgr.create_snapshot(twin1)
    snap2 = mgr.create_snapshot(twin2)

    assert snap1.commit_sha == sha1
    assert snap2.commit_sha == sha2

    diff = mgr.compare_snapshots(snap1, snap2)
    assert diff.head_sha == sha2.value
    assert diff.base_sha == sha1.value
