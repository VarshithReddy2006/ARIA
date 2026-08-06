"""Tool Registry Port Protocol."""

from typing import Any, Callable, Dict, Protocol, runtime_checkable

from ria.domain.agent.entities import ToolExecution


@runtime_checkable
class ToolRegistryPort(Protocol):
    """Protocol for Tool Registry managing platform tools."""

    def invoke_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
    ) -> ToolExecution:
        """Invoke named tool with parameters."""
        ...
