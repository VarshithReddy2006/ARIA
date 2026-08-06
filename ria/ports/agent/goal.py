"""Goal Interpreter Port Protocol."""

from typing import Protocol, runtime_checkable

from ria.domain.agent.value_objects import Goal


@runtime_checkable
class GoalInterpreterPort(Protocol):
    """Protocol for interpreting raw user intent into structured Goal."""

    def interpret_goal(
        self,
        raw_description: str,
        repo_id: str,
    ) -> Goal:
        """Interpret natural language request into a Goal."""
        ...
