"""Unit tests for AgentOrchestratorService (Phase 6)."""

from __future__ import annotations


from ria.application.agent_orchestrator import AgentOrchestratorService
from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.agent_execution import (
    ExecutionContext,
    ExecutionPlan,
    ExecutionSession,
    SharedContext,
)
from ria.domain.models.agent_task import AgentTask, TaskPlan
from ria.domain.models.prompt_context import PromptContext
from ria.domain.models.task_id import TaskId


def test_agent_orchestrator_service() -> None:
    svc = AgentOrchestratorService()

    ctx = ExecutionContext(
        repository_id=RepositoryId("repo1"), commit_sha=CommitSha("a" * 40)
    )
    tid = TaskId.for_task("analysis", "task1")
    task = AgentTask(
        task_id=tid,
        title="Analyze",
        description="Analyze code",
        plan=TaskPlan(task_type="analysis"),
    )

    plan = ExecutionPlan(plan_id="p1", tasks=(task,))
    session = ExecutionSession(session_id="s1", context=ctx, plan=plan)

    shared = SharedContext(prompt_context=PromptContext())

    report = svc.execute_plan(session, shared)

    assert report.session_id == "s1"
    assert report.statistics.tasks_succeeded == 1
    assert len(report.task_results) == 1
