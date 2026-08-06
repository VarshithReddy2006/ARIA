"""Reflection Engine Port Protocol."""

from typing import Protocol, runtime_checkable

from ria.domain.agent.entities import ExecutionContext
from ria.domain.agent.value_objects import ReflectionResult


@runtime_checkable
class ReflectionEnginePort(Protocol):
    """Protocol for evaluating intermediate execution results."""

    def reflect(
        self,
        context: ExecutionContext,
    ) -> ReflectionResult:
        """Evaluate context state and produce ReflectionResult."""
        ...
