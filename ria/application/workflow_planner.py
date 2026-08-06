"""Workflow Planner application service.

Converts multi-agent ExecutionPlan into a WorkflowDefinition DAG.
Implements :class:`~ria.ports.workflow.WorkflowPlannerPort`.
"""

from __future__ import annotations

from typing import List

from ria.domain.models.agent_execution import ExecutionPlan
from ria.domain.models.workflow_definition import (
    WorkflowAction,
    WorkflowDefinition,
    WorkflowStep,
)
from ria.domain.models.workflow_execution import WorkflowContext
from ria.domain.models.workflow_id import WorkflowId
from ria.ports.workflow import WorkflowPlannerPort

__all__ = ["WorkflowPlannerService"]


class WorkflowPlannerService(WorkflowPlannerPort):
    """Service for compiling ExecutionPlan into a WorkflowDefinition DAG."""

    def plan_workflow(
        self,
        plan: ExecutionPlan,
        context: WorkflowContext,
    ) -> WorkflowDefinition:
        """Convert ExecutionPlan tasks into WorkflowStep entries."""
        steps: List[WorkflowStep] = []

        for idx, task in enumerate(plan.tasks):
            action_type = (
                "inspection" if task.plan.task_type == "analysis" else "static_analysis"
            )
            action = WorkflowAction(
                action_type=action_type, target=context.repository_id.value
            )
            step_id = f"step_{idx + 1}_{task.task_id.value}"

            requires_approval = task.plan.task_type in (
                "refactoring",
                "repository_modification",
            )
            deps = tuple(f"step_{d.value}" for d in task.dependencies)

            step = WorkflowStep(
                step_id=step_id,
                title=task.title,
                action=action,
                requires_approval=requires_approval,
                dependencies=deps,
            )
            steps.append(step)

        wfid = WorkflowId.for_workflow(plan.plan_id, context.commit_sha.value[:8])
        return WorkflowDefinition(
            workflow_id=wfid,
            name=f"Workflow for {plan.plan_id}",
            description=f"Automated workflow compiled for session {context.session_id}",
            steps=tuple(steps),
        )
