"""Runtime Port Protocol."""

from typing import Protocol, runtime_checkable

from ria.domain.agent.entities import ExecutionResult
from ria.domain.agent.value_objects import Goal


@runtime_checkable
class RuntimePort(Protocol):
    """Protocol for Agent Runtime orchestrating goal execution lifecycle."""

    def execute_goal(
        self,
        goal: Goal,
    ) -> ExecutionResult:
        """Orchestrate full goal execution lifecycle."""
        ...
