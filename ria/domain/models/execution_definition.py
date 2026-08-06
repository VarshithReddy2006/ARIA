"""Execution definition domain models.

Defines ExecutionState, ExecutionAction, and ExecutionDefinition.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Tuple

from ria.domain.models.execution_id import ExecutionId

__all__ = ["ExecutionState", "ExecutionAction", "ExecutionDefinition"]


class ExecutionState(str, Enum):
    """Lifecycle state enum for Repository Execution."""

    PENDING = "pending"
    PREPARING = "preparing"
    APPLYING = "applying"
    VALIDATING = "validating"
    COMMITTING = "committing"
    COMPLETED = "completed"
    FAILED = "failed"
    REVERTED = "reverted"


@dataclass(frozen=True)
class ExecutionAction:
    """Action to be performed during repository execution.

    Attributes:
        action_type: Action type ('create_file', 'modify_file', 'delete_file').
        target_path: Repository-relative target file path.
        content: New file content or replacement content string.
    """

    action_type: str
    target_path: str
    content: str = ""


@dataclass(frozen=True)
class ExecutionDefinition:
    """Specification of a Repository Execution.

    Attributes:
        execution_id: Unique ExecutionId.
        workflow_id: Parent WorkflowId string.
        actions: Tuple of ExecutionAction steps.
    """

    execution_id: ExecutionId
    workflow_id: str
    actions: Tuple[ExecutionAction, ...] = ()
