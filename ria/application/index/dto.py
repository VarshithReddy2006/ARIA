"""Data Transfer Objects for Index Core Application Layer."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, slots=True)
class ScanRepositoryCommand:
    """Command DTO for scanning a repository workspace."""

    repo_id: str
    workspace_path: str


@dataclass(frozen=True, slots=True)
class ExecutePipelineCommand:
    """Command DTO for executing full IndexPipeline over a synchronized repository."""

    repo_id: str
    target_commit_sha: Optional[str] = None


@dataclass(frozen=True, slots=True)
class PipelineResultDTO:
    """DTO summarizing IndexPipeline execution results."""

    batch_id: str
    repo_id: str
    commit_sha: str
    total_files_discovered: int
    total_files_parsed: int
    total_files_failed: int
    elapsed_seconds: float
    is_success: bool
    error_message: Optional[str] = None
