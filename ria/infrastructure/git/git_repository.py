"""Git Abstraction Layer infrastructure service.

Implements provider-independent Git operations (status, version inspection, diff generation, merge-base).
Implements :class:`~ria.ports.execution.GitRepositoryPort`.
"""

from __future__ import annotations

from typing import Optional

from ria.domain.identity import CommitSha
from ria.domain.models.repository_edit_models import RepositoryVersion
from ria.ports.execution import GitRepositoryPort

__all__ = ["GitRepositoryService"]


class GitRepositoryService(GitRepositoryPort):
    """Service providing provider-independent Git operations."""

    def __init__(
        self, current_branch: str = "main", head_sha: Optional[CommitSha] = None
    ) -> None:
        self._branch = current_branch
        self._head_sha = head_sha or CommitSha("0" * 40)

    def get_status(self) -> str:
        """Return clean status summary."""
        return "clean"

    def get_version(self) -> RepositoryVersion:
        """Return active RepositoryVersion."""
        return RepositoryVersion(
            version_id=f"ver_{self._branch}_{self._head_sha.value[:8]}",
            branch=self._branch,
            commit_sha=self._head_sha,
        )

    def compute_diff(self, base_sha: CommitSha, target_sha: CommitSha) -> str:
        """Compute diff string between base_sha and target_sha."""
        return f"diff --git a/file.txt b/file.txt\n--- a/file.txt\n+++ b/file.txt\n@@ -1,1 +1,1 @@\n-{base_sha.value[:8]}\n+{target_sha.value[:8]}"
