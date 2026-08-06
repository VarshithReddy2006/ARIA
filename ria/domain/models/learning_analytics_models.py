"""Learning, analytics, and policy domain models.

Defines LearningRecord, ExecutionHistory, ExecutionAnalytics, and ExecutionPolicy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from ria.domain.models.execution_id import ExecutionId

__all__ = [
    "LearningRecord",
    "ExecutionHistory",
    "ExecutionAnalytics",
    "ExecutionPolicy",
]


@dataclass(frozen=True)
class LearningRecord:
    """Continuous learning insight entry derived from execution performance.

    Attributes:
        record_id: Unique record identifier.
        execution_id: Bound ExecutionId.
        insight_type: Classification insight type ('patch_quality', 'agent_performance', 'duration_opt').
        recommendation: Recommended planning optimization string.
        score: Quality score rating float.
    """

    record_id: str
    execution_id: ExecutionId
    insight_type: str
    recommendation: str
    score: float = 1.0


@dataclass(frozen=True)
class ExecutionHistory:
    """Historical collection of LearningRecord entries.

    Attributes:
        records: Tuple of LearningRecord items.
    """

    records: Tuple[LearningRecord, ...] = ()


@dataclass(frozen=True)
class ExecutionAnalytics:
    """Aggregated statistics for repository execution performance.

    Attributes:
        total_executions: Total execution runs.
        success_rate: Fraction of successful executions [0.0, 1.0].
        avg_duration_seconds: Average execution latency in seconds.
    """

    total_executions: int = 0
    success_rate: float = 1.0
    avg_duration_seconds: float = 0.0

    def __post_init__(self) -> None:
        if self.total_executions < 0:
            raise ValueError("total_executions must be non-negative")
        if not (0.0 <= self.success_rate <= 1.0):
            raise ValueError(
                f"success_rate must be in range [0.0, 1.0], got {self.success_rate}"
            )
        if self.avg_duration_seconds < 0.0:
            raise ValueError(
                f"avg_duration_seconds must be non-negative, got {self.avg_duration_seconds}"
            )


@dataclass(frozen=True)
class ExecutionPolicy:
    """Enforced repository execution safety policy.

    Attributes:
        requires_approval: Enforce approval from Milestone 11.
        max_changed_files: Upper limit on files changed per edit batch.
    """

    requires_approval: bool = True
    max_changed_files: int = 50

    def __post_init__(self) -> None:
        if self.max_changed_files < 1:
            raise ValueError(
                f"max_changed_files must be positive, got {self.max_changed_files}"
            )
