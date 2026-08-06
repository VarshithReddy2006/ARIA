"""Unit tests for Phase 2 execution ports runtime conformance."""

from __future__ import annotations

from typing import Optional, Tuple

from ria.domain.identity import CommitSha
from ria.domain.models.commit_pr_models import (
    CommitMessage,
    CommitPlan,
    PullRequestDraft,
)
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
from ria.ports.execution import (
    BranchManagerPort,
    CommitPlannerPort,
    ExecutionHistoryPort,
    ExecutionStorePort,
    GitRepositoryPort,
    LearningEnginePort,
    PatchGenerationPort,
    PatchValidationPort,
    PullRequestBuilderPort,
    RepositoryEditPort,
)


class DummyRepositoryEdit:
    def apply_edits(
        self, edits: Tuple[RepositoryEdit, ...], dry_run: bool = True
    ) -> ExecutionPatch:
        return ExecutionPatch(patch_id="mock")


class DummyPatchGeneration:
    def generate_patch(self, edits: Tuple[RepositoryEdit, ...]) -> ExecutionPatch:
        return ExecutionPatch(patch_id="mock")


class DummyPatchValidation:
    def validate_patch(self, patch: ExecutionPatch) -> PatchValidation:
        return PatchValidation(is_valid=True)


class DummyGitRepository:
    def get_status(self) -> str:
        return "clean"

    def get_version(self) -> RepositoryVersion:
        return RepositoryVersion(
            version_id="v1", branch="main", commit_sha=CommitSha("a" * 40)
        )

    def compute_diff(self, base_sha: CommitSha, target_sha: CommitSha) -> str:
        return "diff mock"


class DummyBranchManager:
    def create_branch(
        self, branch_name: str, base_commit: CommitSha
    ) -> BranchDefinition:
        return BranchDefinition(branch_name=branch_name, base_commit=base_commit)

    def delete_branch(self, branch_name: str) -> bool:
        return True


class DummyCommitPlanner:
    def prepare_commit(
        self,
        branch_name: str,
        edits: Tuple[RepositoryEdit, ...],
        title: str,
        body: str = "",
    ) -> CommitPlan:
        return CommitPlan(
            plan_id="mock",
            branch_name=branch_name,
            commit_message=CommitMessage(title=title, body=body),
        )


class DummyPullRequestBuilder:
    def build_pull_request(
        self, plan: CommitPlan, summary_text: str
    ) -> PullRequestDraft:
        return PullRequestDraft(
            draft_id="mock",
            title=plan.commit_message.title,
            description=summary_text,
            branch_name=plan.branch_name,
        )


class DummyLearningEngine:
    def record_learning(
        self, execution_id: ExecutionId, is_success: bool, duration_seconds: float
    ) -> LearningRecord:
        return LearningRecord(
            record_id="rec1",
            execution_id=execution_id,
            insight_type="quality",
            recommendation="good",
        )

    def get_analytics(self) -> ExecutionAnalytics:
        return ExecutionAnalytics()


class DummyExecutionHistory:
    def get_history(self) -> ExecutionHistory:
        return ExecutionHistory()


class DummyExecutionStore:
    def get_patch(self, key: ExecutionCacheKey) -> Optional[ExecutionPatch]:
        return None

    def put_patch(self, key: ExecutionCacheKey, patch: ExecutionPatch) -> None:
        pass


def test_execution_ports_conformance() -> None:
    assert isinstance(DummyRepositoryEdit(), RepositoryEditPort)
    assert isinstance(DummyPatchGeneration(), PatchGenerationPort)
    assert isinstance(DummyPatchValidation(), PatchValidationPort)
    assert isinstance(DummyGitRepository(), GitRepositoryPort)
    assert isinstance(DummyBranchManager(), BranchManagerPort)
    assert isinstance(DummyCommitPlanner(), CommitPlannerPort)
    assert isinstance(DummyPullRequestBuilder(), PullRequestBuilderPort)
    assert isinstance(DummyLearningEngine(), LearningEnginePort)
    assert isinstance(DummyExecutionHistory(), ExecutionHistoryPort)
    assert isinstance(DummyExecutionStore(), ExecutionStorePort)
