"""SQLite persistence implementation for Milestone 11 Autonomous Development Workflow Engine.

Implements :class:`~ria.ports.workflow.WorkflowStorePort`.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Optional

from ria.domain.errors import StorageError
from ria.domain.models.workflow_definition import WorkflowState
from ria.domain.models.workflow_execution import WorkflowResult
from ria.domain.models.workflow_id import WorkflowId
from ria.domain.models.workflow_result import WorkflowCacheKey
from ria.infrastructure.storage.sqlite.connection import ConnectionProvider
from ria.ports.workflow import WorkflowStorePort

__all__ = ["SqliteWorkflowStore"]


class SqliteWorkflowStore(WorkflowStorePort):
    """SQLite storage for WorkflowResults and cache."""

    def __init__(self, connections: ConnectionProvider) -> None:
        self._connections = connections

    def get_result(self, key: WorkflowCacheKey) -> Optional[WorkflowResult]:
        digest = key.digest()
        conn = self._connections.connection()
        try:
            cursor = conn.execute(
                "SELECT result_json FROM ria_workflow_cache WHERE cache_key_digest = ?",
                (digest,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            data = json.loads(row[0])
            wfid = WorkflowId(data["workflow_id"])
            state = WorkflowState(data["state"])
            return WorkflowResult(
                workflow_id=wfid,
                state=state,
                output_text=data.get("output_text", ""),
            )
        except Exception as exc:
            raise StorageError(f"failed to read workflow cache entry: {exc}") from exc

    def put_result(self, key: WorkflowCacheKey, result: WorkflowResult) -> None:
        digest = key.digest()
        cached_at = datetime.now(timezone.utc).isoformat()
        result_json = json.dumps(
            {
                "workflow_id": result.workflow_id.value,
                "state": result.state.value,
                "output_text": result.output_text,
            }
        )

        conn = self._connections.connection()
        try:
            conn.execute(
                """
                INSERT INTO ria_workflow_cache (cache_key_digest, result_json, cached_at)
                VALUES (?, ?, ?)
                ON CONFLICT(cache_key_digest) DO UPDATE SET result_json = excluded.result_json, cached_at = excluded.cached_at
                """,
                (digest, result_json, cached_at),
            )
        except Exception as exc:
            raise StorageError(f"failed to write workflow cache entry: {exc}") from exc
