"""Snapshot Manager Port Protocol."""

from typing import Optional, Protocol, runtime_checkable

from ria.domain.snapshot.entities import RepositorySnapshot
from ria.domain.sync.value_objects import CommitReference, RepositoryIdentity


@runtime_checkable
class SnapshotManagerPort(Protocol):
    """Protocol for creating, storing, and loading RepositorySnapshot entities."""

    def create_snapshot(
        self,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
        total_files: int,
        total_symbols: int,
    ) -> RepositorySnapshot:
        """Create and persist a new RepositorySnapshot."""
        ...

    def get_latest_snapshot(
        self,
        repo_id: RepositoryIdentity,
    ) -> Optional[RepositorySnapshot]:
        """Load the most recent RepositorySnapshot for a repository."""
        ...
