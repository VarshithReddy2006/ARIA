"""Unit tests for Milestone 12 Phase 1 Execution Domain Models."""

from __future__ import annotations

import pytest

from ria.domain.identity import CommitSha
from ria.domain.models.commit_pr_models import (
    CommitMessage,
    CommitPlan,
    MergeStrategy,
    PullRequestDraft,
)
from ria.domain.models.execution_definition import (
    ExecutionAction,
    ExecutionDefinition,
)
from ria.domain.models.execution_id import ExecutionId
from ria.domain.models.execution_result_models import (
    ExecutionCacheKey,
    ExecutionFingerprint,
    ExecutionMetadata,
)
from ria.domain.models.learning_analytics_models import (
    ExecutionAnalytics,
    ExecutionHistory,
    ExecutionPolicy,
    LearningRecord,
)
from ria.domain.models.patch_models import (
    ExecutionPatch,
    PatchChunk,
    PatchFile,
    PatchStatistics,
    PatchValidation,
)
from ria.domain.models.repository_edit_models import (
    BranchDefinition,
    RepositoryEdit,
    RepositorySnapshot,
    RepositoryVersion,
)


def test_execution_id_invariants() -> None:
    eid1 = ExecutionId.for_execution("wf1", "inst1")
    eid2 = ExecutionId.for_execution("wf1", "inst1")

    assert eid1 == eid2
    assert str(eid1) == eid1.value

    with pytest.raises(ValueError, match="non-empty string"):
        ExecutionId("")


def test_execution_definition_and_action() -> None:
    eid = ExecutionId.for_execution("wf1", "1")
    act = ExecutionAction(
        action_type="modify_file", target_path="main.py", content="new code"
    )
    defn = ExecutionDefinition(execution_id=eid, workflow_id="wf1", actions=(act,))

    assert defn.execution_id == eid
    assert len(defn.actions) == 1
    assert defn.actions[0].action_type == "modify_file"


def test_patch_models() -> None:
    chunk = PatchChunk(
        start_line=1, end_line=5, target_content="old", replacement_content="new"
    )
    pfile = PatchFile(file_path="main.py", chunks=(chunk,))
    stats = PatchStatistics(files_changed=1, insertions=5, deletions=2)
    val = PatchValidation(is_valid=True)
    patch = ExecutionPatch(patch_id="p1", files=(pfile,), statistics=stats)

    assert len(patch.files) == 1
    assert patch.statistics.insertions == 5
    assert val.is_valid

    with pytest.raises(ValueError, match="Invalid line range"):
        PatchChunk(start_line=5, end_line=1, target_content="", replacement_content="")


def test_repository_edit_and_branch_models() -> None:
    sha = CommitSha("a" * 40)
    edit = RepositoryEdit(
        file_path="main.py", edit_type="modify", new_content="content"
    )
    snap = RepositorySnapshot(snapshot_id="s1", commit_sha=sha, digest="digest1")
    ver = RepositoryVersion(version_id="v1", branch="feature", commit_sha=sha)
    branch = BranchDefinition(branch_name="feature", base_commit=sha)

    assert edit.file_path == "main.py"
    assert snap.digest == "digest1"
    assert ver.branch == "feature"
    assert branch.branch_name == "feature"


def test_commit_and_pr_models() -> None:
    msg = CommitMessage(title="Feat: update main", body="Details")
    edit = RepositoryEdit(
        file_path="main.py", edit_type="modify", new_content="content"
    )
    plan = CommitPlan(
        plan_id="cp1", branch_name="feature", commit_message=msg, edits=(edit,)
    )

    pr = PullRequestDraft(
        draft_id="pr1",
        title="Title",
        description="Desc",
        branch_name="feature",
        merge_strategy=MergeStrategy.SQUASH,
    )

    assert plan.branch_name == "feature"
    assert pr.merge_strategy == MergeStrategy.SQUASH


def test_learning_analytics_and_policy() -> None:
    eid = ExecutionId.for_execution("wf1", "1")
    rec = LearningRecord(
        record_id="lr1",
        execution_id=eid,
        insight_type="quality",
        recommendation="Optimize edits",
    )
    hist = ExecutionHistory(records=(rec,))
    analytics = ExecutionAnalytics(
        total_executions=10, success_rate=0.9, avg_duration_seconds=1.5
    )
    policy = ExecutionPolicy(requires_approval=True, max_changed_files=20)

    assert len(hist.records) == 1
    assert analytics.success_rate == 0.9
    assert policy.max_changed_files == 20


def test_execution_result_and_cache() -> None:
    fp = ExecutionFingerprint(workflow_id_str="wf1", commit_sha_str="a" * 40)
    key = ExecutionCacheKey(fingerprint=fp)
    meta = ExecutionMetadata(execution_id_str="exc1")

    assert key.digest() is not None
    assert meta.execution_id_str == "exc1"
