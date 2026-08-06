"""Unit tests for Milestone 6 Phase 1 Digital Twin Domain Models."""

from __future__ import annotations

import pytest

from datetime import datetime, timezone

from ria.domain.enums import (
    DiagnosticSeverity,
    RepositoryHealth,
    RepositoryStatus,
    TwinState,
)
from ria.domain.identity import CommitSha, Moniker, RepositoryId
from ria.domain.models.consistency_report import ConsistencyReport
from ria.domain.models.graph import Graph
from ria.domain.models.graph_identity import GraphFingerprint
from ria.domain.models.graph_result import GraphMetadata, GraphStatistics
from ria.domain.models.graph_snapshot import GraphSnapshot
from ria.domain.models.repository import Repository
from ria.domain.models.repository_metrics import RepositoryMetrics
from ria.domain.models.repository_state import RepositoryState
from ria.domain.models.repository_twin import RepositoryTwin
from ria.domain.models.synchronization_result import SynchronizationResult
from ria.domain.models.twin_id import TwinId
from ria.domain.models.twin_identity import TwinCacheKey, TwinFingerprint, TwinVersion
from ria.domain.models.twin_result import TwinDiagnostic, TwinMetadata, TwinStatistics
from ria.domain.models.twin_snapshot import TwinSnapshot


def test_twin_id_invariants() -> None:
    tid1 = TwinId.for_repository("repo1")
    tid2 = TwinId.for_repository("repo1")

    assert tid1 == tid2
    assert str(tid1) == tid1.value

    with pytest.raises(ValueError, match="non-empty string"):
        TwinId("")


def test_twin_identity_value_objects() -> None:
    ver = TwinVersion()
    fp = TwinFingerprint(builder_name="test-builder", version=ver)
    key = TwinCacheKey(
        repository_id=RepositoryId("repo1"),
        commit_sha=CommitSha("a" * 40),
        fingerprint=fp,
    )

    assert key.reuse_key == "a" * 40
    assert key.digest() is not None


def test_repository_metrics_invariants() -> None:
    metrics = RepositoryMetrics(
        repository_size_bytes=1000,
        files_count=10,
        symbols_count=50,
        graph_density=1.5,
    )
    assert metrics.files_count == 10
    assert metrics.graph_density == 1.5

    with pytest.raises(ValueError, match="non-negative"):
        RepositoryMetrics(repository_size_bytes=-10)


def test_consistency_report_and_diagnostics() -> None:
    assert RepositoryHealth.HEALTHY == "healthy"
    diag = TwinDiagnostic(
        severity=DiagnosticSeverity.WARNING, message="Mismatch", component="graph"
    )
    report = ConsistencyReport(is_consistent=False, inconsistencies=(diag,))

    assert not report.is_consistent
    assert len(report.inconsistencies) == 1
    assert report.inconsistencies[0].component == "graph"


def test_synchronization_result_invariants() -> None:
    repo_id = RepositoryId("repo1")
    sha = CommitSha("a" * 40)
    res = SynchronizationResult(
        repository_id=repo_id, commit_sha=sha, state=TwinState.SYNCHRONIZED
    )

    assert res.state is TwinState.SYNCHRONIZED
    assert res.duration_seconds == 0.0

    with pytest.raises(ValueError, match="non-negative"):
        SynchronizationResult(
            repository_id=repo_id, commit_sha=sha, duration_seconds=-5.0
        )


def test_repository_state_and_twin() -> None:
    repo_id = RepositoryId("repo1")
    sha = CommitSha("a" * 40)
    state = RepositoryState(
        repository_id=repo_id,
        current_commit_sha=sha,
        loaded_components=("graph", "semantic"),
    )

    assert state.status is RepositoryStatus.ACTIVE
    assert state.twin_state is TwinState.SYNCHRONIZED
    assert "graph" in state.loaded_components


def test_twin_snapshot_and_twin() -> None:
    repo_id = RepositoryId("repo1")
    sha = CommitSha("a" * 40)

    tid = TwinId.for_repository(repo_id)
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
    state = RepositoryState(repository_id=repo_id, current_commit_sha=sha)

    g_fp = GraphFingerprint("builder", "1.0.0")
    g_meta = GraphMetadata("repo1", sha.value)
    g_stats = GraphStatistics()
    g_snap = GraphSnapshot(repo_id, sha, Graph(), g_fp, g_meta, g_stats)

    metrics = RepositoryMetrics()
    meta = TwinMetadata("repo1", sha.value)
    stats = TwinStatistics()

    twin = RepositoryTwin(
        twin_id=tid,
        repository=repo,
        state=state,
        graph_snapshot=g_snap,
        metrics=metrics,
        metadata=meta,
        statistics=stats,
    )

    t_fp = TwinFingerprint("twin-builder")
    snap = TwinSnapshot(
        twin_id=tid, repository_id=repo_id, commit_sha=sha, twin=twin, fingerprint=t_fp
    )

    assert snap.twin == twin
    assert snap.twin.twin_id == tid
