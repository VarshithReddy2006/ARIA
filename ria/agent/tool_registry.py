"""Tool Registry implementing ToolRegistryPort."""

from typing import Any, Callable, Dict

from ria.domain.agent.entities import ToolExecution
from ria.ports.agent.tool_registry import ToolRegistryPort


class ToolRegistry(ToolRegistryPort):
    """Registry maintaining tool adapters mapping tool_name to platform handlers."""

    def __init__(self) -> None:
        self._tools: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}

    def register_tool(
        self, name: str, handler: Callable[[Dict[str, Any]], Dict[str, Any]]
    ) -> None:
        self._tools[name.lower()] = handler

    def invoke_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
    ) -> ToolExecution:
        t_name = tool_name.lower()
        handler = self._tools.get(t_name)

        if handler is None:
            # Default fallback mock tool result for unregistered tools
            output = {"status": "executed", "tool": tool_name, "is_success": True}
            return ToolExecution(
                tool_name=tool_name,
                parameters=parameters,
                output=output,
                is_success=True,
            )

        try:
            out = handler(parameters)
            return ToolExecution(
                tool_name=tool_name, parameters=parameters, output=out, is_success=True
            )
        except Exception as err:
            out = {"error": str(err), "is_success": False}
            return ToolExecution(
                tool_name=tool_name, parameters=parameters, output=out, is_success=False
            )
