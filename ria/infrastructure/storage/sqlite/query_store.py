"""SQLite persistence and cache implementations for Milestone 7 Query Engine.

Implements :class:`~ria.ports.query.QueryCacheStore`.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Dict, Optional

from ria.domain.errors import StorageError
from ria.domain.identity import CommitSha
from ria.domain.models.query_identity import QueryCacheKey
from ria.domain.models.query_result import (
    QueryMatch,
    QueryMetadata,
    QueryResult,
    QueryStatistics,
)
from ria.infrastructure.storage.sqlite.connection import ConnectionProvider
from ria.ports.query import QueryCacheStore

__all__ = ["SqliteQueryStore", "SqliteQueryCacheStore"]


class SqliteQueryStore:
    """SQLite persistence for saved queries and analysis results."""

    def __init__(self, connections: ConnectionProvider) -> None:
        self._connections = connections


class SqliteQueryCacheStore(QueryCacheStore):
    """SQLite implementation of QueryCacheStore."""

    def __init__(self, connections: ConnectionProvider) -> None:
        self._connections = connections

    def get(self, key: QueryCacheKey) -> Optional[QueryResult]:
        digest = key.digest()
        conn = self._connections.connection()
        try:
            cursor = conn.execute(
                "SELECT result_json FROM ria_query_cache WHERE cache_key_digest = ?",
                (digest,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return _deserialize_query_result(json.loads(row[0]))
        except Exception as exc:
            raise StorageError(f"failed to read query cache entry: {exc}") from exc

    def put(self, key: QueryCacheKey, result: QueryResult) -> None:
        digest = key.digest()
        sha = key.commit_sha.value
        fp_digest = key.fingerprint.digest()
        result_json = json.dumps(_serialize_query_result(result), default=str)
        cached_at = datetime.now(timezone.utc).isoformat()

        conn = self._connections.connection()
        try:
            conn.execute(
                """
                INSERT INTO ria_query_cache (cache_key_digest, commit_sha, fingerprint_digest, result_json, cached_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(cache_key_digest) DO UPDATE SET result_json = excluded.result_json, cached_at = excluded.cached_at
                """,
                (digest, sha, fp_digest, result_json, cached_at),
            )
        except Exception as exc:
            raise StorageError(f"failed to write query cache entry: {exc}") from exc

    def invalidate_by_commit(self, commit_sha: CommitSha) -> int:
        conn = self._connections.connection()
        try:
            cursor = conn.execute(
                "DELETE FROM ria_query_cache WHERE commit_sha = ?",
                (commit_sha.value,),
            )
            return cursor.rowcount
        except Exception as exc:
            raise StorageError(
                f"failed to invalidate query cache by commit: {exc}"
            ) from exc


# -- Serialization Helpers --------------------------------------------------


def _serialize_query_result(res: QueryResult) -> Dict[str, Any]:
    return {
        "matches": [
            {
                "id": m.id,
                "kind": m.kind,
                "name": m.name,
                "qualified_name": m.qualified_name,
                "location_path": m.location_path,
                "score": m.score,
            }
            for m in res.matches
        ],
        "statistics": {
            "total_matches": res.statistics.total_matches,
            "execution_time_seconds": res.statistics.execution_time_seconds,
            "nodes_traversed": res.statistics.nodes_traversed,
            "cache_hit": True,  # Cached when reloaded
        },
        "metadata": {
            "query_id": res.metadata.query_id,
            "query_type": res.metadata.query_type,
        },
    }


def _deserialize_query_result(d: Dict[str, Any]) -> QueryResult:
    matches = tuple(
        QueryMatch(
            id=m["id"],
            kind=m["kind"],
            name=m["name"],
            qualified_name=m["qualified_name"],
            location_path=m.get("location_path"),
            score=m.get("score", 1.0),
        )
        for m in d.get("matches", [])
    )
    stats_d = d.get("statistics", {})
    stats = QueryStatistics(
        total_matches=stats_d.get("total_matches", len(matches)),
        execution_time_seconds=stats_d.get("execution_time_seconds", 0.0),
        nodes_traversed=stats_d.get("nodes_traversed", 0),
        cache_hit=stats_d.get("cache_hit", True),
    )
    meta_d = d.get("metadata", {})
    meta = QueryMetadata(
        query_id=meta_d.get("query_id", "cached"),
        query_type=meta_d.get("query_type", "general"),
    )
    return QueryResult(matches=matches, statistics=stats, metadata=meta)
