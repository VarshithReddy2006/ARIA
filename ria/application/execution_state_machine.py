"""Execution State Machine application service.

Enforces valid workflow lifecycle transitions across CREATED, PLANNED, READY, RUNNING,
WAITING_FOR_APPROVAL, PAUSED, SUCCEEDED, FAILED, ROLLED_BACK, and CANCELLED states.
Implements :class:`~ria.ports.workflow.ExecutionStateMachinePort`.
"""

from __future__ import annotations

from typing import Dict, Set

from ria.domain.errors import IllegalStateTransitionError
from ria.domain.models.workflow_definition import WorkflowState
from ria.domain.models.workflow_id import WorkflowId
from ria.ports.workflow import ExecutionStateMachinePort

__all__ = ["ExecutionStateMachineService"]

VALID_TRANSITIONS: Dict[WorkflowState, Set[WorkflowState]] = {
    WorkflowState.CREATED: {WorkflowState.PLANNED, WorkflowState.CANCELLED},
    WorkflowState.PLANNED: {WorkflowState.READY, WorkflowState.CANCELLED},
    WorkflowState.READY: {
        WorkflowState.RUNNING,
        WorkflowState.PAUSED,
        WorkflowState.CANCELLED,
    },
    WorkflowState.RUNNING: {
        WorkflowState.WAITING_FOR_APPROVAL,
        WorkflowState.PAUSED,
        WorkflowState.SUCCEEDED,
        WorkflowState.FAILED,
        WorkflowState.CANCELLED,
    },
    WorkflowState.WAITING_FOR_APPROVAL: {
        WorkflowState.RUNNING,
        WorkflowState.FAILED,
        WorkflowState.CANCELLED,
    },
    WorkflowState.PAUSED: {WorkflowState.RUNNING, WorkflowState.CANCELLED},
    WorkflowState.SUCCEEDED: {WorkflowState.ROLLED_BACK},
    WorkflowState.FAILED: {WorkflowState.ROLLED_BACK},
    WorkflowState.ROLLED_BACK: set(),
    WorkflowState.CANCELLED: set(),
}


class ExecutionStateMachineService(ExecutionStateMachinePort):
    """Service managing workflow execution state machine transitions."""

    def __init__(self) -> None:
        self._states: Dict[str, WorkflowState] = {}

    def current_state(self, workflow_id: WorkflowId) -> WorkflowState:
        """Get current state of workflow_id."""
        return self._states.get(workflow_id.value, WorkflowState.CREATED)

    def transition(
        self, workflow_id: WorkflowId, new_state: WorkflowState
    ) -> WorkflowState:
        """Transition workflow_id to new_state if valid."""
        curr = self.current_state(workflow_id)
        if new_state not in VALID_TRANSITIONS.get(curr, set()):
            raise IllegalStateTransitionError("Workflow", curr.value, new_state.value)
        self._states[workflow_id.value] = new_state
        return new_state
