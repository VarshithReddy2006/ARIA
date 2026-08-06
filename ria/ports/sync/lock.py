"""Repository Lock Port abstraction."""

from typing import Protocol, runtime_checkable

from ria.domain.sync.value_objects import RepositoryIdentity


@runtime_checkable
class RepositoryLockPort(Protocol):
    """Protocol for cross-process concurrency locking of repository operations.

    Preconditions: TTL seconds must be > 0.
    Postconditions: Acquire returns True if lock obtained, False if busy. Release guarantees lock removal.
    """

    def acquire_lock(self, repo_id: RepositoryIdentity, ttl_seconds: float = 300.0) -> bool:
        """Attempt to acquire process lock for repository with expiration timeout."""
        ...

    def release_lock(self, repo_id: RepositoryIdentity) -> None:
        """Release process lock held for repository."""
        ...

    def is_locked(self, repo_id: RepositoryIdentity) -> bool:
        """Check if repository currently has an active, non-expired lock."""
        ...
