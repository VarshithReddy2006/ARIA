"""Workflow Engine facade and application services (Phases 11 & 13).

Provides unified application services: WorkflowService, ExecutionService, ApprovalService,
VerificationService, RollbackService, AuditService, with metrics sink observability.
"""

from __future__ import annotations

import time
from typing import List, Optional

from ria.application.approval_manager import ApprovalManagerService
from ria.application.audit_logger import AuditLoggerService
from ria.application.execution_state_machine import ExecutionStateMachineService
from ria.application.failure_recovery import FailureRecoveryService
from ria.application.rollback_planner import RollbackPlannerService
from ria.application.tool_execution import ToolExecutionService
from ria.application.verification_pipeline import VerificationPipelineService
from ria.application.workflow_planner import WorkflowPlannerService
from ria.domain.models.workflow_approval import (
    ApprovalDecision,
    ApprovalRequest,
    WorkflowApproval,
)
from ria.domain.models.workflow_audit import AuditEntry, AuditTrail
from ria.domain.models.workflow_definition import WorkflowState
from ria.domain.models.workflow_execution import WorkflowExecution, WorkflowResult
from ria.domain.models.workflow_id import WorkflowId
from ria.domain.models.workflow_verification import VerificationResult
from ria.observability.metrics import NullMetricsSink
from ria.ports.metrics import MetricsSink
from ria.ports.workflow import WorkflowExecutorPort, WorkflowStorePort

__all__ = [
    "WorkflowService",
    "ExecutionService",
    "ApprovalService",
    "VerificationService",
    "RollbackService",
    "AuditService",
]


class ApprovalService:
    """Service wrapping approval management."""

    def __init__(self, approval_manager: ApprovalManagerService) -> None:
        self._approval_manager = approval_manager

    def request_approval(self, request: ApprovalRequest) -> ApprovalRequest:
        return self._approval_manager.request_approval(request)

    def submit_decision(self, approval: WorkflowApproval) -> ApprovalDecision:
        return self._approval_manager.submit_decision(approval)


class VerificationService:
    """Service wrapping verification pipeline."""

    def __init__(self, verifier: VerificationPipelineService) -> None:
        self._verifier = verifier

    def verify(
        self, execution: WorkflowExecution, output_text: str
    ) -> VerificationResult:
        return self._verifier.verify_execution(execution, output_text)


class RollbackService:
    """Service wrapping rollback planning."""

    def __init__(self, rollback_planner: RollbackPlannerService) -> None:
        self._planner = rollback_planner


class AuditService:
    """Service wrapping audit logging."""

    def __init__(self, audit_logger: AuditLoggerService) -> None:
        self._logger = audit_logger

    def get_trail(self, workflow_id: WorkflowId) -> AuditTrail:
        return self._logger.get_trail(workflow_id)


class ExecutionService:
    """Service wrapping execution state machine and tool execution."""

    def __init__(
        self,
        state_machine: ExecutionStateMachineService,
        tool_execution: ToolExecutionService,
    ) -> None:
        self._state_machine = state_machine
        self._tool_execution = tool_execution


class WorkflowService(WorkflowExecutorPort):
    """Facade application service orchestrating end-to-end autonomous workflows with observability."""

    def __init__(
        self,
        workflow_store: Optional[WorkflowStorePort] = None,
        metrics_sink: Optional[MetricsSink] = None,
    ) -> None:
        self._workflow_store = workflow_store
        self._metrics_sink = metrics_sink or NullMetricsSink()

        self._planner = WorkflowPlannerService()
        self._state_machine = ExecutionStateMachineService()
        self._tool_execution = ToolExecutionService()
        self._approval_manager = ApprovalManagerService()
        self._verifier = VerificationPipelineService()
        self._rollback_planner = RollbackPlannerService()
        self._audit_logger = AuditLoggerService()
        self._recovery = FailureRecoveryService(state_machine=self._state_machine)

    def execute_workflow(
        self,
        execution: WorkflowExecution,
    ) -> WorkflowResult:
        """Execute autonomous workflow steps with approval and verification."""
        t0 = time.perf_counter()
        wfid = execution.workflow_id

        # 1. State machine transitions
        self._state_machine.transition(wfid, WorkflowState.PLANNED)
        self._state_machine.transition(wfid, WorkflowState.READY)
        self._state_machine.transition(wfid, WorkflowState.RUNNING)

        self._audit_logger.record_entry(
            AuditEntry(
                entry_id=f"e_{wfid.value}_start",
                workflow_id=wfid,
                event_type="state_change",
                detail="Workflow execution started",
            )
        )

        outputs: List[str] = []

        # 2. Step execution loop
        for step in execution.definition.steps:
            if step.requires_approval:
                req_id = f"req_{wfid.value}_{step.step_id}"
                req = ApprovalRequest(
                    request_id=req_id,
                    workflow_id=wfid,
                    step_id=step.step_id,
                    action_summary=f"Action '{step.action.action_type}' on '{step.action.target}'",
                )
                self._approval_manager.request_approval(req)
                status = self._approval_manager.get_approval_status(req_id)
                if status != ApprovalDecision.APPROVED:
                    self._state_machine.transition(
                        wfid, WorkflowState.WAITING_FOR_APPROVAL
                    )
                    outputs.append(f"Step '{step.title}' paused waiting for approval.")
                    self._metrics_sink.increment("ria.workflow.approvals_waiting")
                    return WorkflowResult(
                        workflow_id=wfid,
                        state=WorkflowState.WAITING_FOR_APPROVAL,
                        output_text="\n".join(outputs),
                    )

            t_step = time.perf_counter()
            step_out = self._tool_execution.execute_action(
                step.action, execution.context
            )
            self._metrics_sink.observe(
                "ria.workflow.step_seconds", time.perf_counter() - t_step
            )
            outputs.append(f"Step '{step.title}': {step_out}")

        output_text = "\n".join(outputs)

        # 3. Verification
        t_ver = time.perf_counter()
        ver_res = self._verifier.verify_execution(execution, output_text)
        self._metrics_sink.observe(
            "ria.workflow.verification_seconds", time.perf_counter() - t_ver
        )

        if not ver_res.is_verified:
            self._state_machine.transition(wfid, WorkflowState.FAILED)
            return WorkflowResult(
                workflow_id=wfid,
                state=WorkflowState.FAILED,
                output_text=output_text,
            )

        self._state_machine.transition(wfid, WorkflowState.SUCCEEDED)
        total_elapsed = time.perf_counter() - t0
        self._metrics_sink.observe("ria.workflow.total_seconds", total_elapsed)

        return WorkflowResult(
            workflow_id=wfid,
            state=WorkflowState.SUCCEEDED,
            output_text=output_text,
        )
