"""Unit tests for TwinConsistencyValidator (Phase 10)."""

from __future__ import annotations

from datetime import datetime, timezone

from ria.application.twin_builder import TwinBuilderService
from ria.application.twin_consistency_validator import TwinConsistencyValidator
from ria.domain.identity import CommitSha, Moniker, RepositoryId
from ria.domain.models.graph import Graph
from ria.domain.models.graph_identity import GraphFingerprint
from ria.domain.models.graph_result import GraphMetadata, GraphStatistics
from ria.domain.models.graph_snapshot import GraphSnapshot
from ria.domain.models.repository import Repository


def test_twin_consistency_validator() -> None:
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

    validator = TwinConsistencyValidator()
    report = validator.validate_consistency(twin)

    assert report.is_consistent
    assert report.repository_to_graph_consistent
    assert len(report.inconsistencies) == 0
