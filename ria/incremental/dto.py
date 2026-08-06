"""Data Transfer Objects for Incremental Subsystem."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, slots=True)
class UpdateRepositoryCommand:
    """Command requesting incremental repository update between commits."""

    repo_id: str
    target_branch: Optional[str] = None


@dataclass(frozen=True, slots=True)
class IncrementalResultDTO:
    """DTO summarizing incremental update execution result."""

    repo_id: str
    from_commit_sha: str
    to_commit_sha: str
    files_reindexed: int
    files_deleted: int
    affected_symbols: int
    elapsed_seconds: float
    is_success: bool
    error_message: Optional[str] = None
