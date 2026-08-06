"""Workflow definition domain models.

Defines WorkflowState, WorkflowAction, WorkflowTransition, WorkflowStep, and WorkflowDefinition.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Tuple

from ria.domain.models.workflow_id import WorkflowId

__all__ = [
    "WorkflowState",
    "WorkflowAction",
    "WorkflowTransition",
    "WorkflowStep",
    "WorkflowDefinition",
]


class WorkflowState(str, Enum):
    """Execution state lifecycle enum for Autonomous Workflows."""

    CREATED = "created"
    PLANNED = "planned"
    READY = "ready"
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    PAUSED = "paused"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class WorkflowAction:
    """Action to be performed within a WorkflowStep.

    Attributes:
        action_type: Type classification of action (e.g. 'inspection', 'static_analysis', 'test', 'verification').
        target: Target identifier or file path.
        params: Immutable parameter map.
    """

    action_type: str
    target: str
    params: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkflowTransition:
    """Transition rule between workflow states.

    Attributes:
        from_state: Source WorkflowState.
        to_state: Target WorkflowState.
        trigger: Trigger event string.
    """

    from_state: WorkflowState
    to_state: WorkflowState
    trigger: str


@dataclass(frozen=True)
class WorkflowStep:
    """Single step in a WorkflowDefinition DAG.

    Attributes:
        step_id: Unique step identifier string within workflow.
        title: Short descriptive title.
        action: Bound WorkflowAction.
        requires_approval: True if step performs repository-changing actions needing approval.
        dependencies: Tuple of step_ids that must complete prior to this step.
    """

    step_id: str
    title: str
    action: WorkflowAction
    requires_approval: bool = False
    dependencies: Tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkflowDefinition:
    """Specification of an Autonomous Workflow.

    Attributes:
        workflow_id: Unique WorkflowId.
        name: Name of workflow.
        description: Functional description.
        steps: Tuple of WorkflowStep items forming execution graph.
    """

    workflow_id: WorkflowId
    name: str
    description: str
    steps: Tuple[WorkflowStep, ...] = ()
