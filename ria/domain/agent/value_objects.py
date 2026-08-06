"""Value Objects for Agent Runtime Subsystem."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Tuple

from ria.domain.common.base import ValueObject
from ria.domain.agent.exceptions import InvalidGoalError


class GoalType(Enum):
    """Supported high-level engineering goal categories."""

    REPOSITORY_EXPLANATION = "REPOSITORY_EXPLANATION"
    ARCHITECTURE_ANALYSIS = "ARCHITECTURE_ANALYSIS"
    CALL_FLOW_ANALYSIS = "CALL_FLOW_ANALYSIS"
    DEPENDENCY_INVESTIGATION = "DEPENDENCY_INVESTIGATION"
    BUG_INVESTIGATION = "BUG_INVESTIGATION"
    DOCUMENTATION_GENERATION = "DOCUMENTATION_GENERATION"
    REFACTORING_ANALYSIS = "REFACTORING_ANALYSIS"
    IMPACT_ANALYSIS = "IMPACT_ANALYSIS"
    CODE_NAVIGATION = "CODE_NAVIGATION"
    REPOSITORY_HEALTH = "REPOSITORY_HEALTH"


class TaskStatus(Enum):
    """Lifecycle execution state for tasks in the DAG graph."""

    PENDING = "PENDING"
    SCHEDULED = "SCHEDULED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class TaskId(ValueObject):
    """Immutable unique identifier for a task."""

    value: str


@dataclass(frozen=True, slots=True)
class CheckpointId(ValueObject):
    """Immutable unique identifier for a snapshot checkpoint."""

    value: str


@dataclass(frozen=True, slots=True)
class Goal(ValueObject):
    """Immutable high-level engineering goal descriptor."""

    goal_id: str
    description: str
    goal_type: GoalType
    repo_id: str

    def _validate_invariants(self) -> None:
        if not self.description or not self.description.strip():
            raise InvalidGoalError("Goal description cannot be empty.")
        if not self.repo_id or not self.repo_id.strip():
            raise InvalidGoalError("Goal repo_id cannot be empty.")


@dataclass(frozen=True, slots=True)
class ExecutionStep(ValueObject):
    """Immutable step specifying a tool invocation in a plan."""

    step_id: str
    tool_name: str
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExecutionPolicy(ValueObject):
    """Immutable configuration for plan execution strategy."""

    max_parallel: int = 4
    timeout_seconds: float = 60.0


@dataclass(frozen=True, slots=True)
class RetryPolicy(ValueObject):
    """Immutable task retry policy."""

    max_retries: int = 3
    backoff_factor: float = 1.5


@dataclass(frozen=True, slots=True)
class ExecutionPlan(ValueObject):
    """Immutable execution plan containing sequence of steps."""

    plan_id: str
    goal: Goal
    steps: Tuple[ExecutionStep, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ReflectionResult(ValueObject):
    """Immutable reflection output evaluating intermediate task results."""

    is_sufficient: bool
    recommended_action: str
    confidence_score: float
    reasoning: str


@dataclass(frozen=True, slots=True)
class VerificationResult(ValueObject):
    """Immutable verification output checking final completion."""

    is_verified: bool
    grounding_pass: bool
    citations_valid: bool
    reasoning: str


@dataclass(frozen=True, slots=True)
class ExecutionStatistics(ValueObject):
    """Immutable statistics summarizing runtime execution timings."""

    planning_ms: float
    execution_ms: float
    reflection_ms: float
    verification_ms: float
    total_tasks: int


@dataclass(frozen=True, slots=True)
class ExecutionSummary(ValueObject):
    """Immutable summary of goal execution."""

    goal_id: str
    is_success: bool
    final_answer: str
    statistics: ExecutionStatistics
