"""Unit tests for ContinuousLearningEngineService (Phase 10)."""

from __future__ import annotations


from ria.application.learning_engine import ContinuousLearningEngineService
from ria.domain.models.execution_id import ExecutionId


def test_learning_engine_service() -> None:
    svc = ContinuousLearningEngineService()
    eid = ExecutionId.for_execution("wf1", "1")

    rec1 = svc.record_learning(eid, is_success=True, duration_seconds=1.2)
    rec2 = svc.record_learning(eid, is_success=False, duration_seconds=12.0)

    assert rec1.score == 1.0
    assert rec2.score == 0.5
    assert rec2.insight_type == "duration_opt"

    analytics = svc.get_analytics()
    assert analytics.total_executions == 2
    assert analytics.success_rate == 0.5

    hist = svc.get_history()
    assert len(hist.records) == 2
