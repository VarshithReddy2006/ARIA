"""Repository edit and branch domain models.

Defines RepositoryEdit, RepositorySnapshot, RepositoryVersion, and BranchDefinition.
"""

from __future__ import annotations

from dataclasses import dataclass

from ria.domain.identity import CommitSha

__all__ = [
    "RepositoryEdit",
    "RepositorySnapshot",
    "RepositoryVersion",
    "BranchDefinition",
]


@dataclass(frozen=True)
class RepositoryEdit:
    """Atomic edit operation on a repository file.

    Attributes:
        file_path: Repository-relative target file path.
        edit_type: Type of edit ('create', 'modify', 'delete').
        new_content: New content string for create/modify.
    """

    file_path: str
    edit_type: str
    new_content: str = ""


@dataclass(frozen=True)
class RepositorySnapshot:
    """Snapshot state record before or after edits.

    Attributes:
        snapshot_id: Unique snapshot identifier.
        commit_sha: Bound CommitSha.
        digest: SHA-256 state digest string.
    """

    snapshot_id: str
    commit_sha: CommitSha
    digest: str


@dataclass(frozen=True)
class RepositoryVersion:
    """Version descriptor for a repository state.

    Attributes:
        version_id: Unique version identifier.
        branch: Git branch name.
        commit_sha: Bound CommitSha.
    """

    version_id: str
    branch: str
    commit_sha: CommitSha


@dataclass(frozen=True)
class BranchDefinition:
    """Git branch specification.

    Attributes:
        branch_name: Target branch name.
        base_commit: Base CommitSha branch was created from.
    """

    branch_name: str
    base_commit: CommitSha
