"""Entities and Containers for Agent Runtime Subsystem."""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from ria.domain.common.base import ValueObject
from ria.domain.agent.value_objects import (
    CheckpointId,
    ExecutionStep,
    Goal,
    ReflectionResult,
    TaskId,
    TaskStatus,
    VerificationResult,
)


@dataclass(frozen=True, slots=True)
class ToolExecution(ValueObject):
    """Immutable record of a tool execution invocation."""

    tool_name: str
    parameters: Dict[str, Any]
    output: Dict[str, Any]
    is_success: bool


@dataclass(frozen=True, slots=True)
class Task(ValueObject):
    """Immutable task node in the execution graph."""

    task_id: TaskId
    step: ExecutionStep
    dependencies: Tuple[TaskId, ...] = field(default_factory=tuple)
    status: TaskStatus = TaskStatus.PENDING
    output: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TaskGraph(ValueObject):
    """Immutable Directed Acyclic Graph (DAG) representing execution tasks."""

    tasks: Tuple[Task, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ExecutionContext(ValueObject):
    """Immutable state container tracking active goal execution context."""

    context_id: str
    goal: Goal
    completed_tasks: Tuple[TaskId, ...] = field(default_factory=tuple)
    intermediate_outputs: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Checkpoint(ValueObject):
    """Immutable execution snapshot for pause/resume and fault recovery."""

    checkpoint_id: CheckpointId
    goal_id: str
    timestamp_str: str
    context_state: Dict[str, Any]


@dataclass(frozen=True, slots=True)
class ExecutionResult(ValueObject):
    """Immutable aggregate output returned from AgentRuntime execution."""

    result_id: str
    goal_id: str
    is_success: bool
    answer_text: str
    reflection: ReflectionResult
    verification: VerificationResult
