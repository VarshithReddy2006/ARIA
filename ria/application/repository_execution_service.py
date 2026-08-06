"""Repository Execution facade and application services (Phases 11 & 13).

Provides unified application services: RepositoryExecutionService, PatchService, GitService,
BranchService, CommitService, PullRequestService, LearningService, with metrics sink observability.
"""

from __future__ import annotations

import time
from typing import Optional, Tuple

from ria.application.branch_manager import BranchManagerService
from ria.application.commit_planner import CommitPlannerService
from ria.application.learning_engine import ContinuousLearningEngineService
from ria.application.patch_generator import PatchGeneratorService
from ria.application.patch_validator import PatchValidatorService
from ria.application.pull_request_builder import PullRequestBuilderService
from ria.application.repository_edit_engine import RepositoryEditEngineService
from ria.domain.models.commit_pr_models import CommitPlan, PullRequestDraft
from ria.domain.models.execution_definition import ExecutionDefinition
from ria.domain.identity import CommitSha
from ria.domain.models.learning_analytics_models import LearningRecord
from ria.domain.models.patch_models import ExecutionPatch, PatchValidation
from ria.domain.models.repository_edit_models import RepositoryEdit
from ria.observability.metrics import NullMetricsSink
from ria.ports.execution import ExecutionStorePort, GitRepositoryPort
from ria.ports.metrics import MetricsSink

__all__ = [
    "RepositoryExecutionService",
    "PatchService",
    "GitService",
    "BranchService",
    "CommitService",
    "PullRequestService",
    "LearningService",
]


class PatchService:
    """Service wrapping patch generation and validation."""

    def __init__(
        self, generator: PatchGeneratorService, validator: PatchValidatorService
    ) -> None:
        self._generator = generator
        self._validator = validator

    def generate_and_validate(
        self, edits: Tuple[RepositoryEdit, ...]
    ) -> Tuple[ExecutionPatch, PatchValidation]:
        patch = self._generator.generate_patch(edits)
        val = self._validator.validate_patch(patch)
        return patch, val


class GitService:
    """Service wrapping Git operations."""

    def __init__(self, git_repo: GitRepositoryPort) -> None:
        self._git_repo = git_repo


class BranchService:
    """Service wrapping branch management."""

    def __init__(self, branch_mgr: BranchManagerService) -> None:
        self._branch_mgr = branch_mgr


class CommitService:
    """Service wrapping commit planning."""

    def __init__(self, commit_planner: CommitPlannerService) -> None:
        self._commit_planner = commit_planner


class PullRequestService:
    """Service wrapping PR building."""

    def __init__(self, pr_builder: PullRequestBuilderService) -> None:
        self._pr_builder = pr_builder


class LearningService:
    """Service wrapping continuous learning engine."""

    def __init__(self, learning_engine: ContinuousLearningEngineService) -> None:
        self._learning_engine = learning_engine


class RepositoryExecutionService:
    """Facade application service orchestrating end-to-end repository execution with observability."""

    def __init__(
        self,
        execution_store: Optional[ExecutionStorePort] = None,
        metrics_sink: Optional[MetricsSink] = None,
        git_repo: Optional[GitRepositoryPort] = None,
    ) -> None:
        self._execution_store = execution_store
        self._metrics_sink = metrics_sink or NullMetricsSink()

        self._edit_engine = RepositoryEditEngineService()
        self._patch_generator = PatchGeneratorService()
        self._patch_validator = PatchValidatorService()
        self._git_repo = git_repo
        self._branch_mgr = BranchManagerService()
        self._commit_planner = CommitPlannerService()
        self._pr_builder = PullRequestBuilderService()
        self._learning_engine = ContinuousLearningEngineService()

    def execute_edits(
        self,
        execution_def: ExecutionDefinition,
        edits: Tuple[RepositoryEdit, ...],
        branch_name: str = "feature-branch",
        commit_title: str = "Feat: repository execution updates",
    ) -> Tuple[ExecutionPatch, CommitPlan, PullRequestDraft, LearningRecord]:
        """Orchestrate safe repository execution, patch generation, commit planning, PR drafting, and continuous learning."""
        t0 = time.perf_counter()

        # 1. Branch definition
        head_sha = (
            self._git_repo.get_version().commit_sha
            if self._git_repo
            else CommitSha("0" * 40)
        )
        branch_def = self._branch_mgr.create_branch(branch_name, head_sha)

        # 2. Patch generation & validation
        t_patch = time.perf_counter()
        patch = self._patch_generator.generate_patch(edits)
        self._metrics_sink.observe(
            "ria.execution.patch_generation_seconds", time.perf_counter() - t_patch
        )

        t_val = time.perf_counter()
        validation = self._patch_validator.validate_patch(patch)
        self._metrics_sink.observe(
            "ria.execution.patch_validation_seconds", time.perf_counter() - t_val
        )

        # 3. Dry-run edit execution
        t_edit = time.perf_counter()
        self._edit_engine.apply_edits(edits, dry_run=True)
        self._metrics_sink.observe(
            "ria.execution.repository_edit_seconds", time.perf_counter() - t_edit
        )

        # 4. Commit planning & PR drafting
        commit_plan = self._commit_planner.prepare_commit(
            branch_name=branch_def.branch_name,
            edits=edits,
            title=commit_title,
            body=f"Execution ID: {execution_def.execution_id.value}\nFiles changed: {len(edits)}",
        )

        pr_draft = self._pr_builder.build_pull_request(
            plan=commit_plan,
            summary_text=f"Repository execution patch applied cleanly. Validation: {validation.is_valid}",
        )

        # 5. Continuous learning recording
        total_elapsed = time.perf_counter() - t0
        self._metrics_sink.observe("ria.execution.total_seconds", total_elapsed)
        self._metrics_sink.increment(
            "ria.execution.success_total"
            if validation.is_valid
            else "ria.execution.failure_total"
        )

        learning_rec = self._learning_engine.record_learning(
            execution_id=execution_def.execution_id,
            is_success=validation.is_valid,
            duration_seconds=total_elapsed,
        )

        return patch, commit_plan, pr_draft, learning_rec
