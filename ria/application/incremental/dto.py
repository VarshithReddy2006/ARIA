"""Data Transfer Objects for Incremental Application Layer."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, slots=True)
class IncrementalUpdateCommandDTO:
    """DTO requesting incremental update execution for a repository."""

    repo_id: str
    target_branch: Optional[str] = None


@dataclass(frozen=True, slots=True)
class SnapshotRefreshCommandDTO:
    """DTO requesting snapshot refresh for a repository."""

    repo_id: str


@dataclass(frozen=True, slots=True)
class PlanGenerationCommandDTO:
    """DTO requesting incremental plan generation without execution."""

    repo_id: str
    from_commit_sha: str
    to_commit_sha: str
