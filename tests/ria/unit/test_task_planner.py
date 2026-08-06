"""Unit tests for TaskPlannerService (Phase 3)."""

from __future__ import annotations


from ria.application.task_planner import TaskPlannerService
from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.agent_execution import ExecutionContext


def test_task_planner_service() -> None:
    planner = TaskPlannerService()
    ctx = ExecutionContext(
        repository_id=RepositoryId("repo1"), commit_sha=CommitSha("a" * 40)
    )

    plan1 = planner.plan_tasks("Explain dependencies in repo", ctx)
    assert len(plan1.tasks) == 2
    assert plan1.tasks[1].plan.task_type == "dependency"
    assert len(plan1.dependencies) == 1

    plan2 = planner.plan_tasks("General overview", ctx)
    assert len(plan2.tasks) == 2
    assert plan2.tasks[1].plan.task_type == "review"
