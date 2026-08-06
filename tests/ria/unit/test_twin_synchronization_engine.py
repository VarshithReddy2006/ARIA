"""Unit tests for SynchronizationEngine (Phase 6)."""

from __future__ import annotations


from ria.application.twin_synchronization_engine import SynchronizationEngine
from ria.domain.enums import TwinState
from ria.domain.identity import CommitSha, RepositoryId


def test_synchronization_engine() -> None:
    engine = SynchronizationEngine()
    repo_id = RepositoryId("repo1")
    sha = CommitSha("a" * 40)

    res = engine.synchronize(repo_id, sha)

    assert res.repository_id == repo_id
    assert res.commit_sha == sha
    assert res.state is TwinState.SYNCHRONIZED
    assert res.duration_seconds >= 0.0
