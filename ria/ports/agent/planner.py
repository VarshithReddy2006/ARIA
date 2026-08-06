"""Planner Port Protocol."""

from typing import Protocol, runtime_checkable

from ria.domain.agent.value_objects import ExecutionPlan, Goal


@runtime_checkable
class PlannerPort(Protocol):
    """Protocol for constructing deterministic ExecutionPlan."""

    def create_plan(
        self,
        goal: Goal,
    ) -> ExecutionPlan:
        """Generate ExecutionPlan for goal."""
        ...


class ExecutionPlannerPort(Protocol):
    """Protocol for execution planning."""

    ...


class TaskPlannerPort(Protocol):
    """Protocol for task planning."""

    ...
