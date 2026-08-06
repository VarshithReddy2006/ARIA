"""Domain Entities for C0 Repository Sync."""

from dataclasses import dataclass
from typing import Optional

from ria.domain.common.value_objects import Timestamp, UUIDv4
from ria.domain.sync.exceptions import InvalidStateTransitionError
from ria.domain.sync.value_objects import (
    BranchReference,
    CommitReference,
    RepositoryIdentity,
    RepositoryMetadata,
    SyncStatus,
)


@dataclass
class RepositoryState:
    """Aggregate Root representing the lifecycle state of a repository."""

    identity: RepositoryIdentity
    status: SyncStatus
    metadata: RepositoryMetadata
    current_branch: Optional[BranchReference] = None
    current_commit: Optional[CommitReference] = None
    last_synced_at: Optional[Timestamp] = None

    def start_cloning(self) -> None:
        if self.status in (SyncStatus.LOCKED,):
            raise InvalidStateTransitionError(
                "Cannot start cloning a locked repository."
            )
        self.status = SyncStatus.CLONING

    def start_syncing(self) -> None:
        if self.status in (SyncStatus.CLONING, SyncStatus.LOCKED):
            raise InvalidStateTransitionError(
                f"Cannot start syncing from status {self.status.name}."
            )
        self.status = SyncStatus.SYNCING

    def mark_synchronized(
        self,
        branch: BranchReference,
        commit: CommitReference,
        synced_at: Timestamp,
    ) -> None:
        self.current_branch = branch
        self.current_commit = commit
        self.last_synced_at = synced_at
        self.status = SyncStatus.SYNCHRONIZED

    def mark_failed(self) -> None:
        self.status = SyncStatus.FAILED

    def mark_locked(self) -> None:
        self.status = SyncStatus.LOCKED

    def unlock(self) -> None:
        if self.status == SyncStatus.LOCKED:
            self.status = SyncStatus.SYNCHRONIZED


@dataclass
class SyncJob:
    """Entity representing an executed repository synchronization job."""

    job_id: UUIDv4
    repo_id: RepositoryIdentity
    started_at: Timestamp
    completed_at: Optional[Timestamp] = None
    final_status: SyncStatus = SyncStatus.SYNCING
    error_message: Optional[str] = None

    def complete_success(self, completed_at: Timestamp) -> None:
        self.completed_at = completed_at
        self.final_status = SyncStatus.SYNCHRONIZED

    def complete_failure(self, error_message: str, completed_at: Timestamp) -> None:
        self.completed_at = completed_at
        self.final_status = SyncStatus.FAILED
        self.error_message = error_message
