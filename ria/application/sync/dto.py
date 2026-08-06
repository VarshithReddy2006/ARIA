"""Data Transfer Objects for Repository Sync Application Layer."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, slots=True)
class RegisterRepositoryCommand:
    """Command DTO for registering a new repository."""

    remote_url: str
    name: str
    default_branch: str = "main"


@dataclass(frozen=True, slots=True)
class SynchronizeRepositoryCommand:
    """Command DTO for synchronizing an existing repository."""

    repo_id: str
    target_branch: Optional[str] = None


@dataclass(frozen=True, slots=True)
class SyncStatusDTO:
    """DTO summarizing repository sync lifecycle status."""

    repo_id: str
    remote_url: str
    name: str
    status: str
    current_branch: Optional[str]
    current_commit_sha: Optional[str]
    file_count: int
    total_bytes: int
    last_synced_at: Optional[str]


@dataclass(frozen=True, slots=True)
class SyncResultDTO:
    """DTO summarizing synchronization execution result."""

    repo_id: str
    is_success: bool
    status: str
    current_commit_sha: str
    files_changed: int
    elapsed_seconds: float
    error_message: Optional[str] = None
