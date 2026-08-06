"""Integration tests for SqliteExecutionStore (Phase 12)."""

from __future__ import annotations

import pytest

from ria.domain.models.execution_result_models import (
    ExecutionCacheKey,
    ExecutionFingerprint,
)
from ria.domain.models.patch_models import (
    ExecutionPatch,
    PatchChunk,
    PatchFile,
    PatchStatistics,
)
from ria.infrastructure.storage.sqlite.connection import ConnectionProvider
from ria.infrastructure.storage.sqlite.execution_store import SqliteExecutionStore
from ria.infrastructure.storage.sqlite.migrations import MigrationRunner


@pytest.fixture
def execution_db() -> ConnectionProvider:
    provider = ConnectionProvider(":memory:")
    runner = MigrationRunner(provider)
    runner.run()
    return provider


def test_sqlite_execution_store(execution_db: ConnectionProvider) -> None:
    store = SqliteExecutionStore(execution_db)

    fp = ExecutionFingerprint(workflow_id_str="wf1", commit_sha_str="a" * 40)
    key = ExecutionCacheKey(fingerprint=fp)

    chunk = PatchChunk(
        start_line=1, end_line=5, target_content="a", replacement_content="b"
    )
    pfile = PatchFile(file_path="main.py", chunks=(chunk,))
    stats = PatchStatistics(files_changed=1, insertions=5, deletions=0)
    patch = ExecutionPatch(patch_id="patch1", files=(pfile,), statistics=stats)

    store.put_patch(key, patch)
    retrieved = store.get_patch(key)

    assert retrieved is not None
    assert retrieved.patch_id == "patch1"
    assert retrieved.statistics.files_changed == 1
    assert retrieved.files[0].file_path == "main.py"
