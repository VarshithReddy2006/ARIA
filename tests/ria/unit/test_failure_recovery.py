"""Unit tests for FailureRecoveryService (Phase 10)."""

from __future__ import annotations


from ria.application.execution_state_machine import ExecutionStateMachineService
from ria.application.failure_recovery import FailureRecoveryService
from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.workflow_definition import WorkflowDefinition, WorkflowState
from ria.domain.models.workflow_execution import (
    WorkflowContext,
    WorkflowExecution,
    WorkflowFailure,
)
from ria.domain.models.workflow_id import WorkflowId


def test_failure_recovery_service() -> None:
    sm = ExecutionStateMachineService()
    svc = FailureRecoveryService(state_machine=sm)

    wfid = WorkflowId.for_workflow("wf", "1")
    sm.transition(wfid, WorkflowState.PLANNED)
    sm.transition(wfid, WorkflowState.READY)
    sm.transition(wfid, WorkflowState.RUNNING)

    defn = WorkflowDefinition(wfid, "Name", "Desc")
    ctx = WorkflowContext(RepositoryId("repo1"), CommitSha("a" * 40), "s1")
    exec_rec = WorkflowExecution(wfid, defn, ctx, current_state=WorkflowState.RUNNING)
    fail = WorkflowFailure(wfid, "step1", "Transient error")

    res = svc.recover(exec_rec, fail, strategy="retry")
    assert res.state == WorkflowState.SUCCEEDED
    assert "Recovered" in res.output_text
