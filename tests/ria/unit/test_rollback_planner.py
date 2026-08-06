"""Unit tests for RollbackPlannerService (Phase 8)."""

from __future__ import annotations


from ria.application.rollback_planner import RollbackPlannerService
from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.workflow_definition import (
    WorkflowAction,
    WorkflowDefinition,
    WorkflowStep,
)
from ria.domain.models.workflow_execution import WorkflowContext, WorkflowExecution
from ria.domain.models.workflow_id import WorkflowId
from ria.domain.models.workflow_rollback import ExecutionCheckpoint


def test_rollback_planner_service() -> None:
    svc = RollbackPlannerService()

    wfid = WorkflowId.for_workflow("wf", "1")
    act1 = WorkflowAction("inspection", "file1.py")
    act2 = WorkflowAction("inspection", "file2.py")

    step1 = WorkflowStep("step1", "S1", act1)
    step2 = WorkflowStep("step2", "S2", act2)
    defn = WorkflowDefinition(wfid, "Name", "Desc", (step1, step2))

    ctx = WorkflowContext(RepositoryId("repo1"), CommitSha("a" * 40), "s1")
    exec_rec = WorkflowExecution(wfid, defn, ctx)
    cp = ExecutionCheckpoint("cp1", "step1")

    rb_plan = svc.plan_rollback(exec_rec, cp)

    assert len(rb_plan.actions) == 1
    assert rb_plan.actions[0].step_id == "step2"
    assert svc.execute_rollback(rb_plan)
