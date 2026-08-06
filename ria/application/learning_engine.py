"""Continuous Learning Engine application service.

Learns from execution success, failures, verification results, latency, and patch quality
to derive planning optimization recommendations without retraining LLMs.
Implements :class:`~ria.ports.execution.LearningEnginePort` and :class:`~ria.ports.execution.ExecutionHistoryPort`.
"""

from __future__ import annotations

from typing import List

from ria.domain.models.execution_id import ExecutionId
from ria.domain.models.learning_analytics_models import (
    ExecutionAnalytics,
    ExecutionHistory,
    LearningRecord,
)
from ria.ports.execution import ExecutionHistoryPort, LearningEnginePort

__all__ = ["ContinuousLearningEngineService"]


class ContinuousLearningEngineService(LearningEnginePort, ExecutionHistoryPort):
    """Service deriving learning insights and analytics from execution statistics."""

    def __init__(self) -> None:
        self._records: List[LearningRecord] = []
        self._total_runs = 0
        self._successful_runs = 0
        self._total_duration = 0.0

    def record_learning(
        self,
        execution_id: ExecutionId,
        is_success: bool,
        duration_seconds: float,
    ) -> LearningRecord:
        """Derive and store a LearningRecord based on execution performance."""
        self._total_runs += 1
        if is_success:
            self._successful_runs += 1
        self._total_duration += duration_seconds

        insight_type = "duration_opt" if duration_seconds > 10.0 else "patch_quality"
        rec = (
            "Break into smaller sub-tasks"
            if duration_seconds > 10.0
            else "Maintain current step granularity"
        )
        score = 1.0 if is_success else 0.5

        record = LearningRecord(
            record_id=f"rec_{len(self._records) + 1}_{execution_id.value[:8]}",
            execution_id=execution_id,
            insight_type=insight_type,
            recommendation=rec,
            score=score,
        )
        self._records.append(record)
        return record

    def get_analytics(self) -> ExecutionAnalytics:
        """Return aggregated ExecutionAnalytics."""
        if self._total_runs == 0:
            return ExecutionAnalytics()

        success_rate = self._successful_runs / self._total_runs
        avg_dur = self._total_duration / self._total_runs

        return ExecutionAnalytics(
            total_executions=self._total_runs,
            success_rate=success_rate,
            avg_duration_seconds=avg_dur,
        )

    def get_history(self) -> ExecutionHistory:
        """Retrieve full ExecutionHistory."""
        return ExecutionHistory(records=tuple(self._records))
