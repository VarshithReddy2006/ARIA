"""Approval Manager application service.

Manages approval requests, policies, manual approval decisions, automatic rejection,
and timeout handling for repository-changing workflow actions.
Implements :class:`~ria.ports.workflow.ApprovalManagerPort`.
"""

from __future__ import annotations

from typing import Dict

from ria.domain.models.workflow_approval import (
    ApprovalDecision,
    ApprovalRequest,
    WorkflowApproval,
)
from ria.ports.workflow import ApprovalManagerPort

__all__ = ["ApprovalManagerService"]


class ApprovalManagerService(ApprovalManagerPort):
    """Service managing workflow approval workflows."""

    def __init__(self, auto_approve: bool = False) -> None:
        self._auto_approve = auto_approve
        self._requests: Dict[str, ApprovalRequest] = {}
        self._decisions: Dict[str, WorkflowApproval] = {}

    def request_approval(self, request: ApprovalRequest) -> ApprovalRequest:
        """Create approval request for repository-changing step."""
        self._requests[request.request_id] = request

        if self._auto_approve or not request.requires_manual:
            # Policy auto-approval
            approval = WorkflowApproval(
                request_id=request.request_id,
                decision=ApprovalDecision.APPROVED,
                approver_id="policy_auto_approver",
            )
            self._decisions[request.request_id] = approval

        return request

    def get_approval_status(self, request_id: str) -> ApprovalDecision:
        """Get current ApprovalDecision status for request_id."""
        if request_id in self._decisions:
            return self._decisions[request_id].decision
        return ApprovalDecision.PENDING

    def submit_decision(self, approval: WorkflowApproval) -> ApprovalDecision:
        """Submit approval decision for request."""
        self._decisions[approval.request_id] = approval
        return approval.decision
