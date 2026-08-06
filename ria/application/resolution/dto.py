"""Data Transfer Objects for Resolution Application Layer."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, slots=True)
class ResolveAndStoreCommand:
    """Command DTO for resolving symbols and persisting facts for a synchronized repository."""

    repo_id: str
    commit_sha: Optional[str] = None


@dataclass(frozen=True, slots=True)
class FactSummaryDTO:
    """DTO summarizing stored semantic facts for a repository commit."""

    repo_id: str
    commit_sha: str
    total_symbols: int
    total_definitions: int
    total_references: int
    total_calls: int
    total_imports: int
    total_inheritance: int
    is_success: bool
    error_message: Optional[str] = None
