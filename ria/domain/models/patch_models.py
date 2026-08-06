"""Patch domain models.

Defines PatchChunk, PatchFile, PatchStatistics, PatchValidation, and ExecutionPatch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

__all__ = [
    "PatchChunk",
    "PatchFile",
    "PatchStatistics",
    "PatchValidation",
    "ExecutionPatch",
]


@dataclass(frozen=True)
class PatchChunk:
    """Single line-range chunk replacement within a file patch.

    Attributes:
        start_line: Starting 1-indexed line number.
        end_line: Ending 1-indexed line number.
        target_content: Exact original content string.
        replacement_content: Replacement content string.
    """

    start_line: int
    end_line: int
    target_content: str
    replacement_content: str

    def __post_init__(self) -> None:
        if self.start_line < 1 or self.end_line < self.start_line:
            raise ValueError(f"Invalid line range [{self.start_line}, {self.end_line}]")


@dataclass(frozen=True)
class PatchFile:
    """Patch representation for a single file.

    Attributes:
        file_path: Repository-relative target file path.
        chunks: Tuple of PatchChunk items.
    """

    file_path: str
    chunks: Tuple[PatchChunk, ...] = ()


@dataclass(frozen=True)
class PatchStatistics:
    """Metrics summary for a patch.

    Attributes:
        files_changed: Number of modified files.
        insertions: Total lines added.
        deletions: Total lines removed.
    """

    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0

    def __post_init__(self) -> None:
        if self.files_changed < 0 or self.insertions < 0 or self.deletions < 0:
            raise ValueError("Patch statistics counters must be non-negative")


@dataclass(frozen=True)
class PatchValidation:
    """Validation report for an ExecutionPatch.

    Attributes:
        is_valid: True if patch applies cleanly and passes syntax checks.
        syntax_valid: True if syntax correctness check passed.
        issues: Tuple of reported issue string descriptions.
    """

    is_valid: bool
    syntax_valid: bool = True
    issues: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ExecutionPatch:
    """Collection of file patches representing structured repository edits.

    Attributes:
        patch_id: Unique patch identifier.
        files: Tuple of PatchFile items.
        statistics: PatchStatistics summary.
    """

    patch_id: str
    files: Tuple[PatchFile, ...] = ()
    statistics: PatchStatistics = field(default_factory=PatchStatistics)
