"""Unit tests for SQLite Storage Adapters."""

from ria.domain.common.value_objects import Timestamp, UUIDv4
from ria.domain.sync.entities import RepositoryState
from ria.domain.sync.value_objects import (
    BranchReference,
    CommitReference,
    RepositoryIdentity,
    RepositoryMetadata,
    SyncStatus,
)
from ria.infrastructure.storage import (
    SQLiteRepositoryLockAdapter,
    SQLiteRepositoryRegistryAdapter,
)


def test_sqlite_repository_registry_adapter() -> None:
    registry = SQLiteRepositoryRegistryAdapter(db_path=":memory:")

    identity = RepositoryIdentity(
        repo_id=UUIDv4.generate(),
        remote_url="https://github.com/org/repo.git",
        name="repo",
    )
    metadata = RepositoryMetadata(
        file_count=5,
        total_bytes=500,
        default_branch="main",
        registered_at=Timestamp.now(),
    )
    state = RepositoryState(
        identity=identity,
        status=SyncStatus.UNINITIALIZED,
        metadata=metadata,
    )

    # Save
    registry.save_state(state)

    # Get
    loaded = registry.get_state(identity)
    assert loaded is not None
    assert loaded.identity.name == "repo"
    assert loaded.status == SyncStatus.UNINITIALIZED

    # Update state
    commit = CommitReference(sha="a" * 40, committed_at=Timestamp.now())
    branch = BranchReference(name="main", head_commit=commit)
    state.mark_synchronized(branch=branch, commit=commit, synced_at=Timestamp.now())
    registry.save_state(state)

    updated = registry.get_state(identity)
    assert updated is not None
    assert updated.status == SyncStatus.SYNCHRONIZED
    assert updated.current_commit == commit

    # List & Delete
    all_states = registry.list_all()
    assert len(all_states) == 1

    assert registry.delete_state(identity)
    assert registry.get_state(identity) is None


def test_sqlite_repository_lock_adapter() -> None:
    lock_adapter = SQLiteRepositoryLockAdapter(db_path=":memory:")
    identity = RepositoryIdentity(
        repo_id=UUIDv4.generate(),
        remote_url="https://github.com/org/repo.git",
        name="repo",
    )

    assert not lock_adapter.is_locked(identity)

    # Acquire lock
    assert lock_adapter.acquire_lock(identity, ttl_seconds=10.0)
    assert lock_adapter.is_locked(identity)

    # Double acquire should fail
    assert not lock_adapter.acquire_lock(identity, ttl_seconds=10.0)

    # Release lock
    lock_adapter.release_lock(identity)
    assert not lock_adapter.is_locked(identity)
