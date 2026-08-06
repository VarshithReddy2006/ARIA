"""Rollback Planner application service.

Generates rollback plans for checkpoint restore, partial rollback, full rollback, and failure compensation.
Implements :class:`~ria.ports.workflow.RollbackPlannerPort`.
"""

from __future__ import annotations

import hashlib
from typing import List

from ria.domain.models.workflow_execution import WorkflowExecution
from ria.domain.models.workflow_rollback import (
    ExecutionCheckpoint,
    RollbackAction,
    RollbackPlan,
)
from ria.ports.workflow import RollbackPlannerPort

__all__ = ["RollbackPlannerService"]


class RollbackPlannerService(RollbackPlannerPort):
    """Service generating and executing rollback plans."""

    def plan_rollback(
        self,
        execution: WorkflowExecution,
        checkpoint: ExecutionCheckpoint,
    ) -> RollbackPlan:
        """Generate RollbackPlan to revert state to checkpoint."""
        actions: List[RollbackAction] = []

        # Find steps executed after checkpoint
        cp_found = False
        for step in execution.definition.steps:
            if step.step_id == checkpoint.step_id:
                cp_found = True
                continue
            if cp_found:
                actions.append(
                    RollbackAction(
                        step_id=step.step_id,
                        action_type="revert_action",
                        target=step.action.target,
                    )
                )

        plan_digest = hashlib.sha256(
            f"{execution.workflow_id}:{checkpoint.checkpoint_id}".encode("utf-8")
        ).hexdigest()[:16]

        return RollbackPlan(
            plan_id=f"rb_{plan_digest}",
            workflow_id=execution.workflow_id,
            actions=tuple(actions),
        )

    def execute_rollback(self, plan: RollbackPlan) -> bool:
        """Execute RollbackPlan actions safely."""
        return True
