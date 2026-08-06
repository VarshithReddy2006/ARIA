"""Workflow rollback and checkpoint domain models.

Defines ExecutionCheckpoint, ExecutionSnapshot, RollbackAction, and RollbackPlan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Tuple

from ria.domain.models.workflow_id import WorkflowId

__all__ = [
    "ExecutionCheckpoint",
    "ExecutionSnapshot",
    "RollbackAction",
    "RollbackPlan",
]


@dataclass(frozen=True)
class ExecutionCheckpoint:
    """Restorable execution state checkpoint marker.

    Attributes:
        checkpoint_id: Unique checkpoint identifier.
        step_id: Step identifier checkpoint was created at.
        timestamp_iso: UTC creation timestamp.
    """

    checkpoint_id: str
    step_id: str
    timestamp_iso: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass(frozen=True)
class ExecutionSnapshot:
    """Snapshot data marker for state verification.

    Attributes:
        snapshot_id: Unique snapshot identifier.
        checkpoint_id: Bound checkpoint_id.
        snapshot_digest: Content hash digest of state.
    """

    snapshot_id: str
    checkpoint_id: str
    snapshot_digest: str


@dataclass(frozen=True)
class RollbackAction:
    """Compensating action to revert a workflow step.

    Attributes:
        step_id: Target step_id being reverted.
        action_type: Reversal action type classification.
        target: Target resource identifier.
    """

    step_id: str
    action_type: str
    target: str


@dataclass(frozen=True)
class RollbackPlan:
    """Plan for restoring workflow execution state.

    Attributes:
        plan_id: Unique rollback plan identifier.
        workflow_id: Target WorkflowId.
        actions: Tuple of compensating RollbackAction steps.
    """

    plan_id: str
    workflow_id: WorkflowId
    actions: Tuple[RollbackAction, ...] = ()
