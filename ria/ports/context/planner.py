"""Context Planner Port Definition."""

from typing import Protocol, Any


class ContextPlannerPort(Protocol):
    """Port interface for context planning."""

    def plan_context(self, request: Any) -> Any: ...
