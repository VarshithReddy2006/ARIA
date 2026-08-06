"""Integration tests for Milestone 11 — Autonomous Development Workflow Engine (Phase 15)."""

from __future__ import annotations

import pytest

from ria.application.workflow_planner import WorkflowPlannerService
from ria.application.workflow_service import WorkflowService
from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.agent_execution import ExecutionPlan
from ria.domain.models.agent_task import AgentTask, TaskPlan
from ria.domain.models.task_id import TaskId
from ria.domain.models.workflow_definition import WorkflowState
from ria.domain.models.workflow_execution import WorkflowContext, WorkflowExecution
from ria.infrastructure.storage.sqlite.connection import ConnectionProvider
from ria.infrastructure.storage.sqlite.migrations import MigrationRunner
from ria.infrastructure.storage.sqlite.workflow_store import SqliteWorkflowStore


@pytest.fixture
def workflow_engine_db() -> ConnectionProvider:
    provider = ConnectionProvider(":memory:")
    runner = MigrationRunner(provider)
    runner.run()
    return provider


def test_workflow_engine_end_to_end(workflow_engine_db: ConnectionProvider) -> None:
    store = SqliteWorkflowStore(workflow_engine_db)
    service = WorkflowService(workflow_store=store)
    planner = WorkflowPlannerService()

    repo_id = RepositoryId("repo1")
    sha = CommitSha("a" * 40)
    ctx = WorkflowContext(repository_id=repo_id, commit_sha=sha, session_id="s1")

    tid = TaskId.for_task("analysis", "task1")
    task = AgentTask(
        task_id=tid,
        title="Analyze Repo",
        description="Run analysis",
        plan=TaskPlan(task_type="analysis"),
    )
    plan = ExecutionPlan(plan_id="p1", tasks=(task,))

    # 1. Plan Workflow
    wf_def = planner.plan_workflow(plan, ctx)
    exec_rec = WorkflowExecution(
        workflow_id=wf_def.workflow_id, definition=wf_def, context=ctx
    )

    # 2. Execute Workflow
    res = service.execute_workflow(exec_rec)

    assert res.state == WorkflowState.SUCCEEDED
    assert "Inspected" in res.output_text
