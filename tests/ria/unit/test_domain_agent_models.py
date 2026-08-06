"""Unit tests for Milestone 10 Phase 1 Multi-Agent Domain Models."""

from __future__ import annotations

import pytest

from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.agent_communication import AgentConversation, AgentMessage
from ria.domain.models.agent_definition import (
    AgentCapability,
    AgentDefinition,
    AgentRole,
    AgentState,
)
from ria.domain.models.agent_execution import (
    ExecutionContext,
    ExecutionPlan,
    ExecutionSession,
    SharedContext,
)
from ria.domain.models.agent_id import AgentId
from ria.domain.models.agent_result import (
    AgentCacheKey,
    AgentFingerprint,
    AgentMetadata,
    AgentStatistics,
    ExecutionReport,
)
from ria.domain.models.agent_task import (
    AgentTask,
    TaskAssignment,
    TaskDependency,
    TaskExecution,
    TaskFailure,
    TaskPlan,
    TaskResult,
)
from ria.domain.models.prompt_context import PromptContext
from ria.domain.models.task_id import TaskId


def test_agent_id_and_task_id_invariants() -> None:
    aid1 = AgentId.for_agent("analyst", "instance1")
    aid2 = AgentId.for_agent("analyst", "instance1")
    tid1 = TaskId.for_task("analyze", "title1")

    assert aid1 == aid2
    assert str(aid1) == aid1.value
    assert str(tid1) == tid1.value

    with pytest.raises(ValueError, match="non-empty string"):
        AgentId("")

    with pytest.raises(ValueError, match="non-empty string"):
        TaskId("")


def test_agent_definition_and_role() -> None:
    role = AgentRole(role_name="analyst", description="Repository Analyst")
    cap = AgentCapability(capability_name="code_review")
    aid = AgentId.for_agent("analyst", "1")

    defn = AgentDefinition(
        agent_id=aid, name="Analyst 1", role=role, capabilities=(cap,)
    )

    assert defn.agent_id == aid
    assert defn.state == AgentState.IDLE
    assert len(defn.capabilities) == 1


def test_task_models() -> None:
    tid1 = TaskId.for_task("analyze", "task1")
    tid2 = TaskId.for_task("review", "task2")
    aid = AgentId.for_agent("analyst", "1")

    dep = TaskDependency(parent_task_id=tid1, child_task_id=tid2)
    plan = TaskPlan(task_type="analysis", priority=2, timeout_seconds=30.0)
    task = AgentTask(
        task_id=tid1, title="Analyze Repo", description="Run analysis", plan=plan
    )

    assign = TaskAssignment(task_id=tid1, agent_id=aid)
    exec_rec = TaskExecution(task_id=tid1, agent_id=aid, execution_time_seconds=1.5)
    fail = TaskFailure(task_id=tid1, error_message="Error")
    result = TaskResult(task_id=tid1, agent_id=aid, output_text="Done", failure=None)

    assert dep.parent_task_id == tid1
    assert task.plan.priority == 2
    assert assign.agent_id == aid
    assert exec_rec.execution_time_seconds == 1.5
    assert fail.error_message == "Error"
    assert result.output_text == "Done"


def test_execution_plan_and_session() -> None:
    repo_id = RepositoryId("repo1")
    sha = CommitSha("a" * 40)
    ctx = ExecutionContext(repository_id=repo_id, commit_sha=sha)

    plan = ExecutionPlan(plan_id="plan1")
    session = ExecutionSession(session_id="s1", context=ctx, plan=plan)

    p_ctx = PromptContext()
    shared = SharedContext(prompt_context=p_ctx, version=1)

    assert session.session_id == "s1"
    assert shared.version == 1

    with pytest.raises(ValueError, match="version must be positive"):
        SharedContext(prompt_context=p_ctx, version=0)


def test_agent_communication() -> None:
    aid1 = AgentId.for_agent("analyst", "1")
    aid2 = AgentId.for_agent("reviewer", "2")

    msg = AgentMessage(
        message_id="m1",
        sender_id=aid1,
        recipient_id=aid2,
        message_type="request",
        payload="Review code",
    )
    conv = AgentConversation(messages=(msg,))

    assert msg.sender_id == aid1
    assert len(conv.messages) == 1


def test_agent_result_and_cache() -> None:
    fp = AgentFingerprint(plan_id="plan1", query_text="Analyze repo")
    key = AgentCacheKey(fingerprint=fp)
    stats = AgentStatistics(tasks_scheduled=2, tasks_succeeded=2)
    meta = AgentMetadata(session_id="s1")

    report = ExecutionReport(
        session_id="s1", summary_text="Report summary", statistics=stats
    )

    assert key.digest() is not None
    assert report.statistics.tasks_succeeded == 2
    assert meta.session_id == "s1"
