"""Agent task value objects.

Defines TaskDependency, TaskPlan, AgentTask, TaskAssignment, TaskExecution, TaskFailure, and TaskResult.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from ria.domain.models.agent_id import AgentId
from ria.domain.models.reasoning_result import ReasoningResult
from ria.domain.models.task_id import TaskId

__all__ = [
    "TaskDependency",
    "TaskPlan",
    "AgentTask",
    "TaskAssignment",
    "TaskExecution",
    "TaskFailure",
    "TaskResult",
]


@dataclass(frozen=True)
class TaskDependency:
    """Dependency link between tasks in an execution plan.

    Attributes:
        parent_task_id: TaskId that must complete first.
        child_task_id: TaskId depending on parent completion.
    """

    parent_task_id: TaskId
    child_task_id: TaskId


@dataclass(frozen=True)
class TaskPlan:
    """Planned options for executing an AgentTask.

    Attributes:
        task_type: Classification type of task.
        priority: Priority rank (higher means executed sooner).
        timeout_seconds: Max execution timeout.
    """

    task_type: str
    priority: int = 1
    timeout_seconds: float = 60.0

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0.0:
            raise ValueError(
                f"timeout_seconds must be positive, got {self.timeout_seconds}"
            )


@dataclass(frozen=True)
class AgentTask:
    """A single task assigned within a multi-agent execution plan.

    Attributes:
        task_id: Unique TaskId.
        title: Short title.
        description: Full task instruction description.
        plan: TaskPlan parameters.
        dependencies: Tuple of parent TaskIds.
    """

    task_id: TaskId
    title: str
    description: str
    plan: TaskPlan
    dependencies: Tuple[TaskId, ...] = ()


@dataclass(frozen=True)
class TaskAssignment:
    """Binding assignment of a task to a specific agent.

    Attributes:
        task_id: Target TaskId.
        agent_id: Assigned AgentId.
    """

    task_id: TaskId
    agent_id: AgentId


@dataclass(frozen=True)
class TaskExecution:
    """Record of an agent task execution.

    Attributes:
        task_id: TaskId executed.
        agent_id: AgentId executing task.
        execution_time_seconds: Latency in seconds.
    """

    task_id: TaskId
    agent_id: AgentId
    execution_time_seconds: float = 0.0


@dataclass(frozen=True)
class TaskFailure:
    """Failure record for an unfulfilled task.

    Attributes:
        task_id: Failed TaskId.
        error_message: Error description string.
        exception_type: Exception type class name.
    """

    task_id: TaskId
    error_message: str
    exception_type: str = "TaskExecutionError"


@dataclass(frozen=True)
class TaskResult:
    """Result produced by executing an AgentTask.

    Attributes:
        task_id: TaskId executed.
        agent_id: AgentId executing task.
        output_text: Text output generated.
        reasoning_result: Optional bound ReasoningResult from Milestone 9.
        failure: Optional TaskFailure details.
    """

    task_id: TaskId
    agent_id: AgentId
    output_text: str = ""
    reasoning_result: Optional[ReasoningResult] = None
    failure: Optional[TaskFailure] = None
