"""Workflow execution domain models.

Defines WorkflowContext, WorkflowExecution, WorkflowFailure, and WorkflowResult.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.workflow_definition import WorkflowDefinition, WorkflowState
from ria.domain.models.workflow_id import WorkflowId

__all__ = [
    "WorkflowContext",
    "WorkflowExecution",
    "WorkflowFailure",
    "WorkflowResult",
]


@dataclass(frozen=True)
class WorkflowContext:
    """Execution context bound to repository and session.

    Attributes:
        repository_id: Repository identifier.
        commit_sha: Commit SHA.
        session_id: Bound session identifier.
    """

    repository_id: RepositoryId
    commit_sha: CommitSha
    session_id: str


@dataclass(frozen=True)
class WorkflowExecution:
    """Execution tracking record for an active or completed workflow.

    Attributes:
        workflow_id: WorkflowId executed.
        definition: WorkflowDefinition specification.
        context: Bound WorkflowContext.
        current_state: Current WorkflowState.
        started_at_iso: UTC start timestamp.
    """

    workflow_id: WorkflowId
    definition: WorkflowDefinition
    context: WorkflowContext
    current_state: WorkflowState = WorkflowState.CREATED
    started_at_iso: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass(frozen=True)
class WorkflowFailure:
    """Failure record for a failed step or workflow.

    Attributes:
        workflow_id: Target WorkflowId.
        step_id: Step identifier where failure occurred.
        error_message: Detailed error text.
        exception_type: Exception type class name.
    """

    workflow_id: WorkflowId
    step_id: str
    error_message: str
    exception_type: str = "WorkflowExecutionError"


@dataclass(frozen=True)
class WorkflowResult:
    """Final result container of a workflow execution.

    Attributes:
        workflow_id: Target WorkflowId.
        state: Terminal WorkflowState.
        output_text: Unified execution output summary text.
        failure: Optional WorkflowFailure details if state is FAILED.
    """

    workflow_id: WorkflowId
    state: WorkflowState
    output_text: str = ""
    failure: Optional[WorkflowFailure] = None
