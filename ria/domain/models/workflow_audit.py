"""Workflow audit logging domain models.

Defines AuditEntry and AuditTrail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Tuple

from ria.domain.models.workflow_id import WorkflowId

__all__ = ["AuditEntry", "AuditTrail"]


@dataclass(frozen=True)
class AuditEntry:
    """Immutable audit trail log record.

    Attributes:
        entry_id: Unique entry identifier.
        workflow_id: Target WorkflowId.
        event_type: Classification event type ('state_change', 'approval', 'tool_exec', 'verification', 'rollback').
        detail: Detailed event description text.
        timestamp_iso: UTC event timestamp.
    """

    entry_id: str
    workflow_id: WorkflowId
    event_type: str
    detail: str
    timestamp_iso: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass(frozen=True)
class AuditTrail:
    """Sequence log of audit entries for a workflow session.

    Attributes:
        entries: Tuple of AuditEntry items.
    """

    entries: Tuple[AuditEntry, ...] = ()
