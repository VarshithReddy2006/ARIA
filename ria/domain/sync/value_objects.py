"""Value Objects for C0 Repository Sync Domain."""

import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

from ria.domain.common.base import ValueObject
from ria.domain.common.value_objects import Timestamp, UUIDv4
from ria.domain.sync.exceptions import InvalidBranchRefError, InvalidCommitRefError


class SyncStatus(Enum):
    """Lifecycle sync status of a repository."""

    UNINITIALIZED = "UNINITIALIZED"
    CLONING = "CLONING"
    SYNCHRONIZED = "SYNCHRONIZED"
    SYNCING = "SYNCING"
    STALE = "STALE"
    FAILED = "FAILED"
    LOCKED = "LOCKED"


@dataclass(frozen=True, slots=True)
class RepositoryIdentity(ValueObject):
    """Immutable identity of a repository."""

    repo_id: UUIDv4
    remote_url: str
    name: str

    def _validate_invariants(self) -> None:
        if not self.remote_url or not self.remote_url.strip():
            raise ValueError("Repository remote URL cannot be empty.")
        if not self.name or not self.name.strip():
            raise ValueError("Repository name cannot be empty.")


@dataclass(frozen=True, slots=True)
class CommitReference(ValueObject):
    """Immutable reference to a Git commit."""

    sha: str
    committed_at: Timestamp

    def _validate_invariants(self) -> None:
        if not re.match(r"^[0-9a-fA-F]{40}$", self.sha):
            raise InvalidCommitRefError(f"Commit SHA must be a 40-character hex string, got '{self.sha}'.")


@dataclass(frozen=True, slots=True)
class BranchReference(ValueObject):
    """Immutable reference to a Git branch."""

    name: str
    head_commit: CommitReference

    def _validate_invariants(self) -> None:
        if not self.name or not self.name.strip():
            raise InvalidBranchRefError("Branch name cannot be empty.")


@dataclass(frozen=True, slots=True)
class RepositoryMetadata(ValueObject):
    """Immutable metadata describing a repository snapshot."""

    file_count: int
    total_bytes: int
    default_branch: str
    registered_at: Timestamp

    def _validate_invariants(self) -> None:
        if self.file_count < 0:
            raise ValueError("File count cannot be negative.")
        if self.total_bytes < 0:
            raise ValueError("Total bytes cannot be negative.")
        if not self.default_branch or not self.default_branch.strip():
            raise ValueError("Default branch cannot be empty.")


@dataclass(frozen=True, slots=True)
class SyncResult(ValueObject):
    """Immutable result of a repository synchronization operation."""

    is_success: bool
    files_changed: int
    previous_commit: Optional[CommitReference]
    new_commit: CommitReference
    elapsed_seconds: float
    error_message: Optional[str] = None

    def _validate_invariants(self) -> None:
        if self.files_changed < 0:
            raise ValueError("Files changed cannot be negative.")
        if self.elapsed_seconds < 0.0:
            raise ValueError("Elapsed seconds cannot be negative.")
