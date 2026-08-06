"""Unit tests for TwinUpdateService (Phase 7)."""

from __future__ import annotations

from datetime import datetime, timezone

from ria.application.twin_builder import TwinBuilderService
from ria.application.twin_update_service import TwinUpdateService
from ria.domain.identity import CommitSha, Moniker, RepositoryId
from ria.domain.models.change_set import ChangeSet
from ria.domain.models.graph import Graph
from ria.domain.models.graph_identity import GraphFingerprint
from ria.domain.models.graph_result import GraphMetadata, GraphStatistics
from ria.domain.models.graph_snapshot import GraphSnapshot
from ria.domain.models.repository import Repository


def test_incremental_twin_update() -> None:
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

    change_set = ChangeSet(
        head_sha=sha2.value, base_sha=sha1.value, added=frozenset({"src/new_file.py"})
    )
    svc = TwinUpdateService(twin_builder=builder)
    updated_twin = svc.update_twin(twin1, change_set, g_snap2)

    assert updated_twin.state.current_commit_sha == sha2
