"""Unit tests for Milestone 11 Phase 1 Workflow Domain Models."""

from __future__ import annotations

import pytest

from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.workflow_approval import (
    ApprovalDecision,
    ApprovalRequest,
    WorkflowApproval,
)
from ria.domain.models.workflow_audit import AuditEntry, AuditTrail
from ria.domain.models.workflow_definition import (
    WorkflowAction,
    WorkflowDefinition,
    WorkflowState,
    WorkflowStep,
    WorkflowTransition,
)
from ria.domain.models.workflow_execution import (
    WorkflowContext,
    WorkflowExecution,
    WorkflowFailure,
    WorkflowResult,
)
from ria.domain.models.workflow_id import WorkflowId
from ria.domain.models.workflow_result import (
    WorkflowCacheKey,
    WorkflowFingerprint,
    WorkflowMetadata,
    WorkflowStatistics,
)
from ria.domain.models.workflow_rollback import (
    ExecutionCheckpoint,
    ExecutionSnapshot,
    RollbackAction,
    RollbackPlan,
)
from ria.domain.models.workflow_verification import VerificationResult


def test_workflow_id_invariants() -> None:
    wfid1 = WorkflowId.for_workflow("refactoring", "instance1")
    wfid2 = WorkflowId.for_workflow("refactoring", "instance1")

    assert wfid1 == wfid2
    assert str(wfid1) == wfid1.value

    with pytest.raises(ValueError, match="non-empty string"):
        WorkflowId("")


def test_workflow_definition_and_steps() -> None:
    wfid = WorkflowId.for_workflow("refactor", "1")
    act = WorkflowAction(action_type="inspection", target="main.py")
    step = WorkflowStep(
        step_id="step1", title="Inspect Main", action=act, requires_approval=False
    )

    trans = WorkflowTransition(
        from_state=WorkflowState.CREATED, to_state=WorkflowState.PLANNED, trigger="plan"
    )
    defn = WorkflowDefinition(
        workflow_id=wfid,
        name="Refactor Workflow",
        description="Refactoring steps",
        steps=(step,),
    )

    assert defn.workflow_id == wfid
    assert len(defn.steps) == 1
    assert trans.from_state == WorkflowState.CREATED


def test_workflow_execution_and_context() -> None:
    repo_id = RepositoryId("repo1")
    sha = CommitSha("a" * 40)
    ctx = WorkflowContext(repository_id=repo_id, commit_sha=sha, session_id="s1")

    wfid = WorkflowId.for_workflow("refactor", "1")
    defn = WorkflowDefinition(workflow_id=wfid, name="Name", description="Desc")

    exec_rec = WorkflowExecution(workflow_id=wfid, definition=defn, context=ctx)
    fail = WorkflowFailure(workflow_id=wfid, step_id="step1", error_message="Failed")
    result = WorkflowResult(
        workflow_id=wfid, state=WorkflowState.SUCCEEDED, output_text="Done"
    )

    assert exec_rec.current_state == WorkflowState.CREATED
    assert fail.error_message == "Failed"
    assert result.state == WorkflowState.SUCCEEDED


def test_workflow_approval_models() -> None:
    wfid = WorkflowId.for_workflow("refactor", "1")
    req = ApprovalRequest(
        request_id="req1",
        workflow_id=wfid,
        step_id="step1",
        action_summary="Modify repo",
    )
    appr = WorkflowApproval(
        request_id="req1", decision=ApprovalDecision.APPROVED, approver_id="user1"
    )

    assert req.requires_manual
    assert appr.decision == ApprovalDecision.APPROVED


def test_workflow_rollback_and_checkpoints() -> None:
    wfid = WorkflowId.for_workflow("refactor", "1")
    cp = ExecutionCheckpoint(checkpoint_id="cp1", step_id="step1")
    snap = ExecutionSnapshot(
        snapshot_id="snap1", checkpoint_id="cp1", snapshot_digest="digest1"
    )

    act = RollbackAction(step_id="step1", action_type="revert", target="main.py")
    plan = RollbackPlan(plan_id="plan1", workflow_id=wfid, actions=(act,))

    assert cp.step_id == "step1"
    assert snap.snapshot_digest == "digest1"
    assert len(plan.actions) == 1


def test_workflow_audit_and_verification() -> None:
    wfid = WorkflowId.for_workflow("refactor", "1")
    entry = AuditEntry(
        entry_id="e1",
        workflow_id=wfid,
        event_type="state_change",
        detail="Transition to RUNNING",
    )
    trail = AuditTrail(entries=(entry,))

    ver = VerificationResult(is_verified=True, tool_success=True)

    assert len(trail.entries) == 1
    assert ver.is_verified


def test_workflow_result_and_cache() -> None:
    fp = WorkflowFingerprint(workflow_name="refactor", commit_sha="a" * 40)
    key = WorkflowCacheKey(fingerprint=fp)
    stats = WorkflowStatistics(steps_total=2, steps_completed=2)
    meta = WorkflowMetadata(workflow_id_str="wf1")

    assert key.digest() is not None
    assert stats.steps_completed == 2
    assert meta.workflow_id_str == "wf1"
