"""Execution Engine Port Protocol."""

from typing import Protocol, runtime_checkable

from ria.domain.agent.entities import ExecutionContext
from ria.domain.agent.value_objects import ExecutionPlan
from ria.ports.agent.tool_registry import ToolRegistryPort


@runtime_checkable
class ExecutionEnginePort(Protocol):
    """Protocol for executing TaskGraph via ToolRegistryPort."""

    def execute_plan(
        self,
        plan: ExecutionPlan,
        tool_registry: ToolRegistryPort,
    ) -> ExecutionContext:
        """Execute plan and return ExecutionContext."""
        ...
