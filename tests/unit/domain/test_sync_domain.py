"""Unit tests for C0 Repository Sync domain invariants."""

import pytest
from ria.domain.common.value_objects import Timestamp, UUIDv4
from ria.domain.sync import (
    BranchReference,
    CommitReference,
    InvalidCommitRefError,
    RepositoryIdentity,
    RepositoryMetadata,
    RepositoryState,
    SyncStatus,
)


def test_repository_identity_valid() -> None:
    uuid = UUIDv4.generate()
    identity = RepositoryIdentity(
        repo_id=uuid,
        remote_url="https://github.com/org/repo.git",
        name="repo",
    )
    assert identity.name == "repo"
    assert identity.remote_url == "https://github.com/org/repo.git"


def test_repository_identity_invalid() -> None:
    uuid = UUIDv4.generate()
    with pytest.raises(ValueError, match="remote URL cannot be empty"):
        RepositoryIdentity(repo_id=uuid, remote_url="", name="repo")


def test_commit_reference_validation() -> None:
    valid_sha = "a" * 40
    ts = Timestamp.now()
    ref = CommitReference(sha=valid_sha, committed_at=ts)
    assert ref.sha == valid_sha

    with pytest.raises(InvalidCommitRefError):
        CommitReference(sha="invalid_sha", committed_at=ts)


def test_repository_state_transitions() -> None:
    identity = RepositoryIdentity(
        repo_id=UUIDv4.generate(),
        remote_url="https://github.com/org/repo.git",
        name="repo",
    )
    metadata = RepositoryMetadata(
        file_count=10,
        total_bytes=1000,
        default_branch="main",
        registered_at=Timestamp.now(),
    )
    state = RepositoryState(
        identity=identity,
        status=SyncStatus.UNINITIALIZED,
        metadata=metadata,
    )

    state.start_cloning()
    assert state.status == SyncStatus.CLONING

    commit = CommitReference(sha="b" * 40, committed_at=Timestamp.now())
    branch = BranchReference(name="main", head_commit=commit)
    synced_at = Timestamp.now()

    state.mark_synchronized(branch=branch, commit=commit, synced_at=synced_at)
    assert state.status == SyncStatus.SYNCHRONIZED
    assert state.current_commit == commit
