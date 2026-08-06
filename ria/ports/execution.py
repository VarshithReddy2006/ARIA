"""Port protocols for Milestone 12 — Repository Execution & Continuous Learning Engine.

Defines runtime checkable protocols for repository editing, patch generation, patch validation,
git abstraction, branch management, commit planning, pull request building, continuous learning,
execution history, and execution store.
"""

from __future__ import annotations

from typing import Optional, Protocol, Tuple, runtime_checkable

from ria.domain.identity import CommitSha
from ria.domain.models.commit_pr_models import CommitPlan, PullRequestDraft
from ria.domain.models.execution_id import ExecutionId
from ria.domain.models.execution_result_models import ExecutionCacheKey
from ria.domain.models.learning_analytics_models import (
    ExecutionAnalytics,
    ExecutionHistory,
    LearningRecord,
)
from ria.domain.models.patch_models import ExecutionPatch, PatchValidation
from ria.domain.models.repository_edit_models import (
    BranchDefinition,
    RepositoryEdit,
    RepositoryVersion,
)

__all__ = [
    "RepositoryEditPort",
    "PatchGenerationPort",
    "PatchValidationPort",
    "GitRepositoryPort",
    "BranchManagerPort",
    "CommitPlannerPort",
    "PullRequestBuilderPort",
    "LearningEnginePort",
    "ExecutionHistoryPort",
    "ExecutionStorePort",
]


@runtime_checkable
class RepositoryEditPort(Protocol):
    """Port for structured, atomic, read-before-write repository file modifications."""

    def apply_edits(
        self,
        edits: Tuple[RepositoryEdit, ...],
        dry_run: bool = True,
    ) -> ExecutionPatch:
        """Apply batch of RepositoryEdits with dry-run support."""
        ...


@runtime_checkable
class PatchGenerationPort(Protocol):
    """Port for generating unified multi-file execution patches."""

    def generate_patch(
        self,
        edits: Tuple[RepositoryEdit, ...],
    ) -> ExecutionPatch:
        """Construct ExecutionPatch with statistics from edits."""
        ...


@runtime_checkable
class PatchValidationPort(Protocol):
    """Port for validating patch integrity, syntax, and dependency consistency."""

    def validate_patch(
        self,
        patch: ExecutionPatch,
    ) -> PatchValidation:
        """Validate ExecutionPatch."""
        ...


@runtime_checkable
class GitRepositoryPort(Protocol):
    """Port for provider-independent Git operations (status, diffs, merge-base, synchronization)."""

    def get_status(self) -> str:
        """Return clean/dirty status summary."""
        ...

    def get_version(self) -> RepositoryVersion:
        """Return current RepositoryVersion."""
        ...

    def compute_diff(self, base_sha: CommitSha, target_sha: CommitSha) -> str:
        """Compute diff output between two commits."""
        ...


@runtime_checkable
class BranchManagerPort(Protocol):
    """Port for managing Git branch creation, naming policies, and lifecycle."""

    def create_branch(
        self, branch_name: str, base_commit: CommitSha
    ) -> BranchDefinition:
        """Create a new branch."""
        ...

    def delete_branch(self, branch_name: str) -> bool:
        """Delete an existing branch."""
        ...


@runtime_checkable
class CommitPlannerPort(Protocol):
    """Port for generating structured commit plans without automatically pushing."""

    def prepare_commit(
        self,
        branch_name: str,
        edits: Tuple[RepositoryEdit, ...],
        title: str,
        body: str = "",
    ) -> CommitPlan:
        """Prepare a CommitPlan."""
        ...


@runtime_checkable
class PullRequestBuilderPort(Protocol):
    """Port for constructing PullRequestDraft packages."""

    def build_pull_request(
        self,
        plan: CommitPlan,
        summary_text: str,
    ) -> PullRequestDraft:
        """Build PullRequestDraft."""
        ...


@runtime_checkable
class LearningEnginePort(Protocol):
    """Port for continuous learning from execution outcomes to optimize future metadata."""

    def record_learning(
        self,
        execution_id: ExecutionId,
        is_success: bool,
        duration_seconds: float,
    ) -> LearningRecord:
        """Derive and store a LearningRecord."""
        ...

    def get_analytics(self) -> ExecutionAnalytics:
        """Return aggregated ExecutionAnalytics."""
        ...


@runtime_checkable
class ExecutionHistoryPort(Protocol):
    """Port for querying execution history and learning records."""

    def get_history(self) -> ExecutionHistory:
        """Retrieve full ExecutionHistory."""
        ...


@runtime_checkable
class ExecutionStorePort(Protocol):
    """Port for durable persistence of execution cache and history."""

    def get_patch(self, key: ExecutionCacheKey) -> Optional[ExecutionPatch]:
        """Get cached ExecutionPatch."""
        ...

    def put_patch(self, key: ExecutionCacheKey, patch: ExecutionPatch) -> None:
        """Cache ExecutionPatch."""
        ...
