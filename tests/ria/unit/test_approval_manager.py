"""Unit tests for ApprovalManagerService (Phase 6)."""

from __future__ import annotations


from ria.application.approval_manager import ApprovalManagerService
from ria.domain.models.workflow_approval import (
    ApprovalDecision,
    ApprovalRequest,
    WorkflowApproval,
)
from ria.domain.models.workflow_id import WorkflowId


def test_approval_manager_service() -> None:
    svc = ApprovalManagerService(auto_approve=False)
    wfid = WorkflowId.for_workflow("wf", "1")
    req = ApprovalRequest(
        request_id="req1",
        workflow_id=wfid,
        step_id="step1",
        action_summary="Modify code",
    )

    svc.request_approval(req)
    assert svc.get_approval_status("req1") == ApprovalDecision.PENDING

    appr = WorkflowApproval(
        request_id="req1", decision=ApprovalDecision.APPROVED, approver_id="user1"
    )
    dec = svc.submit_decision(appr)

    assert dec == ApprovalDecision.APPROVED
    assert svc.get_approval_status("req1") == ApprovalDecision.APPROVED
