"""Integration tests for Milestone 12 — Repository Execution & Continuous Learning Engine (Phase 15)."""

from __future__ import annotations

import pytest

from ria.application.repository_execution_service import RepositoryExecutionService
from ria.domain.models.execution_definition import ExecutionAction, ExecutionDefinition
from ria.domain.models.execution_id import ExecutionId
from ria.domain.models.repository_edit_models import RepositoryEdit
from ria.infrastructure.storage.sqlite.connection import ConnectionProvider
from ria.infrastructure.storage.sqlite.execution_store import SqliteExecutionStore
from ria.infrastructure.storage.sqlite.migrations import MigrationRunner


@pytest.fixture
def execution_engine_db() -> ConnectionProvider:
    provider = ConnectionProvider(":memory:")
    runner = MigrationRunner(provider)
    runner.run()
    return provider


def test_repository_execution_engine_end_to_end(
    execution_engine_db: ConnectionProvider,
) -> None:
    store = SqliteExecutionStore(execution_engine_db)
    service = RepositoryExecutionService(execution_store=store)

    eid = ExecutionId.for_execution("wf1", "inst1")
    act = ExecutionAction(
        action_type="modify_file", target_path="main.py", content="print('hello world')"
    )
    exec_def = ExecutionDefinition(execution_id=eid, workflow_id="wf1", actions=(act,))

    edit = RepositoryEdit(
        file_path="main.py", edit_type="modify", new_content="print('hello world')"
    )

    # Orchestrate execution
    patch, commit_plan, pr_draft, learning_rec = service.execute_edits(
        execution_def=exec_def,
        edits=(edit,),
        branch_name="feature-updates",
        commit_title="Feat: update main.py",
    )

    assert patch.statistics.files_changed == 1
    assert commit_plan.branch_name == "feature-updates"
    assert pr_draft.title == "Feat: update main.py"
    assert learning_rec.score == 1.0
