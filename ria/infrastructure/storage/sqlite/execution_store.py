"""SQLite persistence implementation for Milestone 12 Repository Execution & Continuous Learning Engine.

Implements :class:`~ria.ports.execution.ExecutionStorePort`.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Optional

from ria.domain.errors import StorageError
from ria.domain.models.execution_result_models import ExecutionCacheKey
from ria.domain.models.patch_models import (
    ExecutionPatch,
    PatchChunk,
    PatchFile,
    PatchStatistics,
)
from ria.infrastructure.storage.sqlite.connection import ConnectionProvider
from ria.ports.execution import ExecutionStorePort

__all__ = ["SqliteExecutionStore"]


class SqliteExecutionStore(ExecutionStorePort):
    """SQLite storage for ExecutionPatch and cache."""

    def __init__(self, connections: ConnectionProvider) -> None:
        self._connections = connections

    def get_patch(self, key: ExecutionCacheKey) -> Optional[ExecutionPatch]:
        digest = key.digest()
        conn = self._connections.connection()
        try:
            cursor = conn.execute(
                "SELECT patch_json FROM ria_execution_cache WHERE cache_key_digest = ?",
                (digest,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            data = json.loads(row[0])
            patch_files = [
                PatchFile(
                    file_path=pf["file_path"],
                    chunks=tuple(
                        PatchChunk(
                            start_line=c["start_line"],
                            end_line=c["end_line"],
                            target_content=c["target_content"],
                            replacement_content=c["replacement_content"],
                        )
                        for c in pf["chunks"]
                    ),
                )
                for pf in data.get("files", [])
            ]
            stats_data = data.get("statistics", {})
            stats = PatchStatistics(
                files_changed=stats_data.get("files_changed", 0),
                insertions=stats_data.get("insertions", 0),
                deletions=stats_data.get("deletions", 0),
            )
            return ExecutionPatch(
                patch_id=data["patch_id"],
                files=tuple(patch_files),
                statistics=stats,
            )
        except Exception as exc:
            raise StorageError(f"failed to read execution cache entry: {exc}") from exc

    def put_patch(self, key: ExecutionCacheKey, patch: ExecutionPatch) -> None:
        digest = key.digest()
        cached_at = datetime.now(timezone.utc).isoformat()
        patch_json = json.dumps(
            {
                "patch_id": patch.patch_id,
                "statistics": {
                    "files_changed": patch.statistics.files_changed,
                    "insertions": patch.statistics.insertions,
                    "deletions": patch.statistics.deletions,
                },
                "files": [
                    {
                        "file_path": pf.file_path,
                        "chunks": [
                            {
                                "start_line": c.start_line,
                                "end_line": c.end_line,
                                "target_content": c.target_content,
                                "replacement_content": c.replacement_content,
                            }
                            for c in pf.chunks
                        ],
                    }
                    for pf in patch.files
                ],
            }
        )

        conn = self._connections.connection()
        try:
            conn.execute(
                """
                INSERT INTO ria_execution_cache (cache_key_digest, patch_json, cached_at)
                VALUES (?, ?, ?)
                ON CONFLICT(cache_key_digest) DO UPDATE SET patch_json = excluded.patch_json, cached_at = excluded.cached_at
                """,
                (digest, patch_json, cached_at),
            )
        except Exception as exc:
            raise StorageError(f"failed to write execution cache entry: {exc}") from exc
