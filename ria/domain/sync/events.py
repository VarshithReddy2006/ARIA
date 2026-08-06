"""Domain Events for C0 Repository Sync."""

from dataclasses import dataclass

from ria.domain.common.value_objects import Timestamp
from ria.domain.sync.value_objects import CommitReference, RepositoryIdentity, SyncStatus


@dataclass(frozen=True, slots=True)
class RepositoryRegisteredEvent:
    """Emitted when a new repository is registered."""

    identity: RepositoryIdentity
    default_branch: str
    occurred_at: Timestamp


@dataclass(frozen=True, slots=True)
class RepositorySyncStartedEvent:
    """Emitted when repository sync begins."""

    identity: RepositoryIdentity
    target_branch: str
    occurred_at: Timestamp


@dataclass(frozen=True, slots=True)
class RepositorySyncedEvent:
    """Emitted when repository sync completes successfully."""

    identity: RepositoryIdentity
    commit: CommitReference
    files_changed: int
    elapsed_seconds: float
    occurred_at: Timestamp


@dataclass(frozen=True, slots=True)
class RepositorySyncFailedEvent:
    """Emitted when repository sync fails."""

    identity: RepositoryIdentity
    error_message: str
    occurred_at: Timestamp
