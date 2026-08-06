"""Unit tests for RepositoryStateManager (Phase 4)."""

from __future__ import annotations


from ria.application.repository_state_manager import RepositoryStateManager
from ria.domain.enums import TwinState
from ria.domain.identity import CommitSha, RepositoryId


def test_repository_state_manager() -> None:
    mgr = RepositoryStateManager()
    repo_id = RepositoryId("repo1")
    sha1 = CommitSha("1" * 40)
    sha2 = CommitSha("2" * 40)

    state = mgr.initialize_state(repo_id, sha1, "main")
    assert state.current_commit_sha == sha1
    assert state.twin_state is TwinState.INITIALIZING

    updated = mgr.transition_state(repo_id, TwinState.SYNCHRONIZED)
    assert updated.twin_state is TwinState.SYNCHRONIZED

    updated2 = mgr.update_commit_and_branch(repo_id, sha2, "feature")
    assert updated2.current_commit_sha == sha2
    assert updated2.current_branch == "feature"

    final_state = mgr.register_loaded_components(repo_id, ("graph", "semantic"))
    assert "graph" in final_state.loaded_components
