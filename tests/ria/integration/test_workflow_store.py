"""Integration tests for SqliteWorkflowStore (Phase 12)."""

from __future__ import annotations

import pytest

from ria.domain.models.workflow_definition import WorkflowState
from ria.domain.models.workflow_execution import WorkflowResult
from ria.domain.models.workflow_id import WorkflowId
from ria.domain.models.workflow_result import WorkflowCacheKey, WorkflowFingerprint
from ria.infrastructure.storage.sqlite.connection import ConnectionProvider
from ria.infrastructure.storage.sqlite.migrations import MigrationRunner
from ria.infrastructure.storage.sqlite.workflow_store import SqliteWorkflowStore


@pytest.fixture
def workflow_db() -> ConnectionProvider:
    provider = ConnectionProvider(":memory:")
    runner = MigrationRunner(provider)
    runner.run()
    return provider


def test_sqlite_workflow_store(workflow_db: ConnectionProvider) -> None:
    store = SqliteWorkflowStore(workflow_db)

    fp = WorkflowFingerprint(workflow_name="refactor", commit_sha="a" * 40)
    key = WorkflowCacheKey(fingerprint=fp)

    wfid = WorkflowId.for_workflow("refactor", "1")
    result = WorkflowResult(
        workflow_id=wfid, state=WorkflowState.SUCCEEDED, output_text="Success"
    )

    store.put_result(key, result)
    retrieved = store.get_result(key)

    assert retrieved is not None
    assert retrieved.workflow_id == wfid
    assert retrieved.state == WorkflowState.SUCCEEDED
    assert retrieved.output_text == "Success"
