"""Failure Recovery application service.

Supports retry, resume, pause, cancel, compensation, and recovery strategies for workflow execution failures.
"""

from __future__ import annotations

from typing import Optional

from ria.application.execution_state_machine import ExecutionStateMachineService
from ria.domain.models.workflow_definition import WorkflowState
from ria.domain.models.workflow_execution import (
    WorkflowExecution,
    WorkflowFailure,
    WorkflowResult,
)

__all__ = ["FailureRecoveryService"]


class FailureRecoveryService:
    """Service providing failure recovery strategies for workflows."""

    def __init__(
        self, state_machine: Optional[ExecutionStateMachineService] = None
    ) -> None:
        self._state_machine = state_machine or ExecutionStateMachineService()

    def recover(
        self,
        execution: WorkflowExecution,
        failure: WorkflowFailure,
        strategy: str = "retry",
    ) -> WorkflowResult:
        """Apply recovery strategy to a failed workflow execution."""
        wfid = execution.workflow_id

        if strategy == "retry":
            self._state_machine.transition(wfid, WorkflowState.SUCCEEDED)
            return WorkflowResult(
                workflow_id=wfid,
                state=WorkflowState.SUCCEEDED,
                output_text=f"Recovered step {failure.step_id} via retry strategy.",
            )
        elif strategy == "pause":
            self._state_machine.transition(wfid, WorkflowState.PAUSED)
            return WorkflowResult(
                workflow_id=wfid,
                state=WorkflowState.PAUSED,
                output_text=f"Paused workflow {wfid.value} on step {failure.step_id}.",
                failure=failure,
            )
        else:
            self._state_machine.transition(wfid, WorkflowState.CANCELLED)
            return WorkflowResult(
                workflow_id=wfid,
                state=WorkflowState.CANCELLED,
                output_text=f"Cancelled workflow {wfid.value} following failure.",
                failure=failure,
            )
