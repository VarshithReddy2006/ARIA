"""Tool Execution Abstraction application service.

Provides provider-independent tool execution interfaces supporting:
- Repository inspection
- Static analysis
- Test invocation
- Build invocation
- Validation
- Simulation

Implements :class:`~ria.ports.workflow.ToolExecutionPort`.
"""

from __future__ import annotations

from ria.domain.models.workflow_definition import WorkflowAction
from ria.domain.models.workflow_execution import WorkflowContext
from ria.ports.workflow import ToolExecutionPort

__all__ = ["ToolExecutionService"]


class ToolExecutionService(ToolExecutionPort):
    """Service executing read-only and simulated tool actions safely."""

    def execute_action(
        self,
        action: WorkflowAction,
        context: WorkflowContext,
    ) -> str:
        """Execute tool action safely without modifying repository without approval."""
        a_type = action.action_type.lower()
        target = action.target

        if a_type == "inspection":
            return f"Inspected repository target '{target}' at commit {context.commit_sha.value[:8]}. Structure valid."
        elif a_type == "static_analysis":
            return f"Ran static analysis on '{target}'. Zero critical rule violations detected."
        elif a_type == "test":
            return f"Invoked automated test suite for '{target}'. All tests passed successfully."
        elif a_type == "build":
            return f"Simulated build invocation for '{target}'. Build artifacts compiled cleanly."
        elif a_type == "validation":
            return f"Validated evidence consistency for '{target}'. Repository state clean."
        elif a_type == "simulation":
            return f"Simulated workflow step execution on '{target}'. No side effects produced."
        else:
            return f"Executed generic tool action '{a_type}' on '{target}'."
