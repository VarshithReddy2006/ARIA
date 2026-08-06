"""Unit tests for ResultAggregatorService (Phase 9)."""

from __future__ import annotations


from ria.application.result_aggregator import ResultAggregatorService
from ria.domain.models.agent_id import AgentId
from ria.domain.models.agent_task import TaskResult
from ria.domain.models.task_id import TaskId


def test_result_aggregator_service() -> None:
    svc = ResultAggregatorService()
    tid = TaskId.for_task("analysis", "task1")
    aid = AgentId.for_agent("analyst", "1")

    res1 = TaskResult(task_id=tid, agent_id=aid, output_text="Analysis complete")
    report = svc.aggregate_results("session1", (res1,))

    assert report.session_id == "session1"
    assert "Analysis complete" in report.summary_text
    assert report.statistics.tasks_succeeded == 1
