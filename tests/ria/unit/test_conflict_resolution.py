"""Unit tests for ConflictResolutionService (Phase 10)."""

from __future__ import annotations


from ria.application.conflict_resolution import ConflictResolutionService
from ria.domain.models.agent_id import AgentId
from ria.domain.models.agent_task import TaskResult
from ria.domain.models.task_id import TaskId


def test_conflict_resolution_service() -> None:
    svc = ConflictResolutionService()
    tid = TaskId.for_task("analysis", "task1")
    aid = AgentId.for_agent("analyst", "1")

    res1 = TaskResult(task_id=tid, agent_id=aid, output_text="Output A")
    res2 = TaskResult(task_id=tid, agent_id=aid, output_text="Output A")  # Duplicate

    resolved = svc.resolve_conflicts((res1, res2))

    assert len(resolved) == 1
    assert resolved[0].output_text == "Output A"
