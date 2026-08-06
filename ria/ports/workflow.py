"""Port protocols for Milestone 11 — Autonomous Development Workflow Engine.

Defines runtime checkable protocols for workflow planning, workflow execution, execution state machine,
tool execution abstraction, approval manager, verification pipeline, rollback planner, audit logging,
workflow registry, and workflow store.
"""

from __future__ import annotations

from typing import Optional, Protocol, Tuple, runtime_checkable

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

__all__ = [
    "WorkflowPlannerPort",
    "WorkflowExecutorPort",
    "ExecutionStateMachinePort",
    "ToolExecutionPort",
    "ApprovalManagerPort",
    "VerificationPipelinePort",
    "RollbackPlannerPort",
    "AuditLogPort",
    "WorkflowRegistryPort",
    "WorkflowStorePort",
]


@runtime_checkable
class WorkflowPlannerPort(Protocol):
    """Port for planning workflow definitions from multi-agent execution plans."""

    def plan_workflow(
        self,
        plan: ExecutionPlan,
        context: WorkflowContext,
    ) -> WorkflowDefinition:
        """Convert ExecutionPlan into a WorkflowDefinition DAG."""
        ...


@runtime_checkable
class WorkflowExecutorPort(Protocol):
    """Port for executing autonomous workflow steps."""

    def execute_workflow(
        self,
        execution: WorkflowExecution,
    ) -> WorkflowResult:
        """Execute WorkflowExecution with state transitions and verification."""
        ...


@runtime_checkable
class ExecutionStateMachinePort(Protocol):
    """Port for managing workflow execution state machine transitions."""

    def current_state(self, workflow_id: WorkflowId) -> WorkflowState:
        """Return current WorkflowState."""
        ...

    def transition(
        self, workflow_id: WorkflowId, new_state: WorkflowState
    ) -> WorkflowState:
        """Transition workflow execution to new state."""
        ...


@runtime_checkable
class ToolExecutionPort(Protocol):
    """Port for provider-independent tool orchestration (inspection, static analysis, testing, verification, simulation)."""

    def execute_action(
        self,
        action: WorkflowAction,
        context: WorkflowContext,
    ) -> str:
        """Execute tool action safely without modifying repository without approval."""
        ...


@runtime_checkable
class ApprovalManagerPort(Protocol):
    """Port for managing workflow approval requests and policies."""

    def request_approval(self, request: ApprovalRequest) -> ApprovalRequest:
        """Create approval request for repository-changing step."""
        ...

    def submit_decision(self, approval: WorkflowApproval) -> ApprovalDecision:
        """Submit approval decision for request."""
        ...


@runtime_checkable
class VerificationPipelinePort(Protocol):
    """Port for verifying workflow completeness, evidence consistency, and tool results."""

    def verify_execution(
        self,
        execution: WorkflowExecution,
        output_text: str,
    ) -> VerificationResult:
        """Verify execution result against expected outputs and repository integrity."""
        ...


@runtime_checkable
class RollbackPlannerPort(Protocol):
    """Port for generating and executing rollback plans."""

    def plan_rollback(
        self,
        execution: WorkflowExecution,
        checkpoint: ExecutionCheckpoint,
    ) -> RollbackPlan:
        """Generate RollbackPlan to revert state to checkpoint."""
        ...

    def execute_rollback(self, plan: RollbackPlan) -> bool:
        """Execute RollbackPlan actions."""
        ...


@runtime_checkable
class AuditLogPort(Protocol):
    """Port for append-only audit logging."""

    def record_entry(self, entry: AuditEntry) -> None:
        """Record audit log entry."""
        ...

    def get_trail(self, workflow_id: WorkflowId) -> AuditTrail:
        """Retrieve full AuditTrail for workflow."""
        ...


@runtime_checkable
class WorkflowRegistryPort(Protocol):
    """Port for discovering available workflow templates."""

    def get_definition(self, workflow_id: WorkflowId) -> Optional[WorkflowDefinition]:
        """Look up WorkflowDefinition."""
        ...

    def list_definitions(self) -> Tuple[WorkflowDefinition, ...]:
        """List registered WorkflowDefinitions."""
        ...


@runtime_checkable
class WorkflowStorePort(Protocol):
    """Port for durable workflow persistence and cache."""

    def get_result(self, key: WorkflowCacheKey) -> Optional[WorkflowResult]:
        """Get cached WorkflowResult."""
        ...

    def put_result(self, key: WorkflowCacheKey, result: WorkflowResult) -> None:
        """Cache WorkflowResult."""
        ...
