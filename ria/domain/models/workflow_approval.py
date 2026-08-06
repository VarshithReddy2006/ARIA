"""Workflow approval domain models.

Defines ApprovalDecision, ApprovalRequest, and WorkflowApproval.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from ria.domain.models.workflow_id import WorkflowId

__all__ = ["ApprovalDecision", "ApprovalRequest", "WorkflowApproval"]


class ApprovalDecision(str, Enum):
    """Decision status for an ApprovalRequest."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass(frozen=True)
class ApprovalRequest:
    """Request created when a workflow step requires explicit approval.

    Attributes:
        request_id: Unique approval request identifier.
        workflow_id: Target WorkflowId.
        step_id: Target WorkflowStep ID requiring approval.
        action_summary: Human-readable summary of repository action.
        requires_manual: True if manual human intervention is enforced.
    """

    request_id: str
    workflow_id: WorkflowId
    step_id: str
    action_summary: str
    requires_manual: bool = True


@dataclass(frozen=True)
class WorkflowApproval:
    """Recorded approval decision event.

    Attributes:
        request_id: Target request_id.
        decision: ApprovalDecision outcome.
        approver_id: Identifier of approver (user or policy).
        timestamp_iso: UTC decision timestamp.
    """

    request_id: str
    decision: ApprovalDecision
    approver_id: str = "system"
    timestamp_iso: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
