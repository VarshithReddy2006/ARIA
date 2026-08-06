"""Unit tests for TwinBuilderService (Phase 3)."""

from __future__ import annotations

from datetime import datetime, timezone

from ria.application.twin_builder import TwinBuilderService
from ria.domain.identity import CommitSha, Moniker, RepositoryId
from ria.domain.models.graph import Graph
from ria.domain.models.graph_identity import GraphFingerprint
from ria.domain.models.graph_result import GraphMetadata, GraphStatistics
from ria.domain.models.graph_snapshot import GraphSnapshot
from ria.domain.models.repository import Repository


def test_build_twin() -> None:
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
    g_meta = GraphMetadata("repo1", sha.value)
    g_stats = GraphStatistics()
    g_snap = GraphSnapshot(repo_id, sha, Graph(), g_fp, g_meta, g_stats)

    svc = TwinBuilderService()
    twin = svc.build_twin(repo, sha, g_snap)

    assert twin.repository == repo
    assert twin.state.current_commit_sha == sha
    assert twin.metadata.repository_id == "repo1"
