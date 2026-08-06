"""Audit Logger application service.

Records append-only audit trail entries for workflow events, approvals, tool executions,
failures, retries, verification results, and rollback actions.
Implements :class:`~ria.ports.workflow.AuditLogPort`.
"""

from __future__ import annotations

from typing import Dict, List

from ria.domain.models.workflow_audit import AuditEntry, AuditTrail
from ria.domain.models.workflow_id import WorkflowId
from ria.ports.workflow import AuditLogPort

__all__ = ["AuditLoggerService"]


class AuditLoggerService(AuditLogPort):
    """Service implementing append-only audit logging for autonomous workflows."""

    def __init__(self) -> None:
        self._entries: Dict[str, List[AuditEntry]] = {}

    def record_entry(self, entry: AuditEntry) -> None:
        """Record audit log entry."""
        wfid = entry.workflow_id.value
        if wfid not in self._entries:
            self._entries[wfid] = []
        self._entries[wfid].append(entry)

    def get_trail(self, workflow_id: WorkflowId) -> AuditTrail:
        """Retrieve full AuditTrail for workflow."""
        entries = self._entries.get(workflow_id.value, [])
        return AuditTrail(entries=tuple(entries))
