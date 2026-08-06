"""Unit tests for ToolExecutionService (Phase 5)."""

from __future__ import annotations


from ria.application.tool_execution import ToolExecutionService
from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.workflow_definition import WorkflowAction
from ria.domain.models.workflow_execution import WorkflowContext


def test_tool_execution_service() -> None:
    svc = ToolExecutionService()
    ctx = WorkflowContext(
        repository_id=RepositoryId("repo1"),
        commit_sha=CommitSha("a" * 40),
        session_id="s1",
    )

    act_inspect = WorkflowAction(action_type="inspection", target="main.py")
    res1 = svc.execute_action(act_inspect, ctx)
    assert "Inspected" in res1

    act_static = WorkflowAction(action_type="static_analysis", target="main.py")
    res2 = svc.execute_action(act_static, ctx)
    assert "static analysis" in res2
