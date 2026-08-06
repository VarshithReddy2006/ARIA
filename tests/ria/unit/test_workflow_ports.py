"""Unit tests for Phase 2 workflow ports runtime conformance."""

from __future__ import annotations

from typing import Optional, Tuple

from ria.domain.models.agent_execution import ExecutionPlan
from ria.domain.models.workflow_approval import (
    ApprovalDecision,
    ApprovalRequest,
    WorkflowApproval,
)
from ria.domain.models.workflow_audit import AuditEntry, AuditTrail
from ria.domain.models.workflow_definition import (
    WorkflowAction,
    WorkflowDefinition,
    WorkflowState,
)
from ria.domain.models.workflow_execution import (
    WorkflowContext,
    WorkflowExecution,
    WorkflowResult,
)
from ria.domain.models.workflow_id import WorkflowId
from ria.domain.models.workflow_result import WorkflowCacheKey
from ria.domain.models.workflow_rollback import ExecutionCheckpoint, RollbackPlan
from ria.domain.models.workflow_verification import VerificationResult
from ria.ports.workflow import (
    ApprovalManagerPort,
    AuditLogPort,
    ExecutionStateMachinePort,
    RollbackPlannerPort,
    ToolExecutionPort,
    VerificationPipelinePort,
    WorkflowExecutorPort,
    WorkflowPlannerPort,
    WorkflowRegistryPort,
    WorkflowStorePort,
)


class DummyWorkflowPlanner:
    def plan_workflow(
        self, plan: ExecutionPlan, context: WorkflowContext
    ) -> WorkflowDefinition:
        wfid = WorkflowId.for_workflow("mock", "1")
        return WorkflowDefinition(workflow_id=wfid, name="mock", description="mock")


class DummyWorkflowExecutor:
    def execute_workflow(self, execution: WorkflowExecution) -> WorkflowResult:
        return WorkflowResult(
            workflow_id=execution.workflow_id, state=WorkflowState.SUCCEEDED
        )


class DummyExecutionStateMachine:
    def current_state(self, workflow_id: WorkflowId) -> WorkflowState:
        return WorkflowState.CREATED

    def transition(
        self, workflow_id: WorkflowId, new_state: WorkflowState
    ) -> WorkflowState:
        return new_state


class DummyToolExecution:
    def execute_action(self, action: WorkflowAction, context: WorkflowContext) -> str:
        return "mock tool output"


class DummyApprovalManager:
    def request_approval(self, request: ApprovalRequest) -> ApprovalRequest:
        return request

    def submit_decision(self, approval: WorkflowApproval) -> ApprovalDecision:
        return approval.decision


class DummyVerificationPipeline:
    def verify_execution(
        self, execution: WorkflowExecution, output_text: str
    ) -> VerificationResult:
        return VerificationResult(is_verified=True)


class DummyRollbackPlanner:
    def plan_rollback(
        self, execution: WorkflowExecution, checkpoint: ExecutionCheckpoint
    ) -> RollbackPlan:
        return RollbackPlan(plan_id="mock", workflow_id=execution.workflow_id)

    def execute_rollback(self, plan: RollbackPlan) -> bool:
        return True


class DummyAuditLog:
    def record_entry(self, entry: AuditEntry) -> None:
        pass

    def get_trail(self, workflow_id: WorkflowId) -> AuditTrail:
        return AuditTrail()


class DummyWorkflowRegistry:
    def get_definition(self, workflow_id: WorkflowId) -> Optional[WorkflowDefinition]:
        return None

    def list_definitions(self) -> Tuple[WorkflowDefinition, ...]:
        return ()


class DummyWorkflowStore:
    def get_result(self, key: WorkflowCacheKey) -> Optional[WorkflowResult]:
        return None

    def put_result(self, key: WorkflowCacheKey, result: WorkflowResult) -> None:
        pass


def test_workflow_ports_conformance() -> None:
    assert isinstance(DummyWorkflowPlanner(), WorkflowPlannerPort)
    assert isinstance(DummyWorkflowExecutor(), WorkflowExecutorPort)
    assert isinstance(DummyExecutionStateMachine(), ExecutionStateMachinePort)
    assert isinstance(DummyToolExecution(), ToolExecutionPort)
    assert isinstance(DummyApprovalManager(), ApprovalManagerPort)
    assert isinstance(DummyVerificationPipeline(), VerificationPipelinePort)
    assert isinstance(DummyRollbackPlanner(), RollbackPlannerPort)
    assert isinstance(DummyAuditLog(), AuditLogPort)
    assert isinstance(DummyWorkflowRegistry(), WorkflowRegistryPort)
    assert isinstance(DummyWorkflowStore(), WorkflowStorePort)
