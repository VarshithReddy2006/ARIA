"""Unit tests for WorkflowPlannerService (Phase 3)."""

from __future__ import annotations


from ria.application.workflow_planner import WorkflowPlannerService
from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.agent_execution import ExecutionPlan
from ria.domain.models.agent_task import AgentTask, TaskPlan
from ria.domain.models.task_id import TaskId
from ria.domain.models.workflow_execution import WorkflowContext


def test_workflow_planner_service() -> None:
    planner = WorkflowPlannerService()
    ctx = WorkflowContext(
        repository_id=RepositoryId("repo1"),
        commit_sha=CommitSha("a" * 40),
        session_id="s1",
    )

    tid = TaskId.for_task("analysis", "t1")
    task = AgentTask(
        task_id=tid,
        title="Analyze",
        description="Desc",
        plan=TaskPlan(task_type="analysis"),
    )
    plan = ExecutionPlan(plan_id="p1", tasks=(task,))

    wf_def = planner.plan_workflow(plan, ctx)

    assert len(wf_def.steps) == 1
    assert wf_def.steps[0].title == "Analyze"
