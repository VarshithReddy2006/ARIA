"""Unit tests for AuditLoggerService (Phase 9)."""

from __future__ import annotations


from ria.application.audit_logger import AuditLoggerService
from ria.domain.models.workflow_audit import AuditEntry
from ria.domain.models.workflow_id import WorkflowId


def test_audit_logger_service() -> None:
    svc = AuditLoggerService()
    wfid = WorkflowId.for_workflow("wf", "1")
    entry = AuditEntry(
        entry_id="e1",
        workflow_id=wfid,
        event_type="state_change",
        detail="Transition to RUNNING",
    )

    svc.record_entry(entry)
    trail = svc.get_trail(wfid)

    assert len(trail.entries) == 1
    assert trail.entries[0].event_type == "state_change"
