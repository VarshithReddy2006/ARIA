"""Unit tests for ExecutionStateMachineService (Phase 4)."""

from __future__ import annotations

import pytest

from ria.application.execution_state_machine import ExecutionStateMachineService
from ria.domain.errors import IllegalStateTransitionError
from ria.domain.models.workflow_definition import WorkflowState
from ria.domain.models.workflow_id import WorkflowId


def test_execution_state_machine_service() -> None:
    sm = ExecutionStateMachineService()
    wfid = WorkflowId.for_workflow("wf", "1")

    assert sm.current_state(wfid) == WorkflowState.CREATED

    sm.transition(wfid, WorkflowState.PLANNED)
    assert sm.current_state(wfid) == WorkflowState.PLANNED

    sm.transition(wfid, WorkflowState.READY)
    sm.transition(wfid, WorkflowState.RUNNING)
    assert sm.current_state(wfid) == WorkflowState.RUNNING

    with pytest.raises(IllegalStateTransitionError, match="Workflow cannot transition"):
        sm.transition(wfid, WorkflowState.CREATED)
