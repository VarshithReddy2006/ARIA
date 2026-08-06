"""Unit tests for RepositoryTwinService (Phases 12 & 13)."""

from __future__ import annotations

from datetime import datetime, timezone

from ria.application.twin_service import RepositoryTwinService
from ria.domain.enums import TwinState
from ria.domain.identity import CommitSha, Moniker, RepositoryId
from ria.domain.models.graph import Graph
from ria.domain.models.graph_identity import GraphFingerprint
from ria.domain.models.graph_result import GraphMetadata, GraphStatistics
from ria.domain.models.graph_snapshot import GraphSnapshot
from ria.domain.models.repository import Repository


def test_repository_twin_service_facade() -> None:
    svc = RepositoryTwinService()
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

    twin = svc.build_twin(repo, sha, g_snap)
    assert twin.repository == repo

    snap = svc.create_snapshot(twin)
    assert snap.twin_id == twin.twin_id

    sync_res = svc.synchronize(repo_id, sha)
    assert sync_res.state is TwinState.SYNCHRONIZED

    metrics = svc.compute_metrics(twin)
    assert metrics.symbols_count == 0

    report = svc.validate_consistency(twin)
    assert report.is_consistent
