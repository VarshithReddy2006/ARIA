"""SQLite persistence and cache implementations for Milestone 6 Digital Twin.

Implements :class:`~ria.ports.twin.TwinStorePort`, :class:`~ria.ports.twin.TwinCacheStore`,
and :class:`~ria.ports.twin.TwinRepositoryPort`.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Dict, Optional

from ria.domain.enums import RepositoryStatus, TwinState
from ria.domain.identity import CommitSha, Moniker, RepositoryId
from ria.domain.models.graph import Graph
from ria.domain.models.graph_identity import GraphFingerprint
from ria.domain.models.graph_result import GraphMetadata, GraphStatistics
from ria.domain.models.graph_snapshot import GraphSnapshot
from ria.domain.models.repository import Repository
from ria.domain.models.repository_metrics import RepositoryMetrics
from ria.domain.models.repository_state import RepositoryState
from ria.domain.models.repository_twin import RepositoryTwin
from ria.domain.models.twin_id import TwinId
from ria.domain.models.twin_identity import TwinCacheKey, TwinFingerprint
from ria.domain.models.twin_result import TwinMetadata, TwinStatistics
from ria.domain.models.twin_snapshot import TwinSnapshot
from ria.domain.errors import StorageError
from ria.infrastructure.storage.sqlite.connection import ConnectionProvider
from ria.ports.twin import TwinCacheStore, TwinRepositoryPort, TwinStorePort

__all__ = ["SqliteTwinStore", "SqliteTwinCacheStore", "SqliteTwinRepository"]


class SqliteTwinRepository(TwinRepositoryPort):
    """SQLite implementation of TwinRepositoryPort for RepositoryState persistence."""

    def __init__(self, connections: ConnectionProvider) -> None:
        self._connections = connections

    def get_state(self, repository_id: RepositoryId) -> Optional[RepositoryState]:
        conn = self._connections.connection()
        try:
            cursor = conn.execute(
                """
                SELECT repository_id, current_commit_sha, current_branch, status, twin_state, loaded_components_json
                FROM ria_twin_state WHERE repository_id = ?
                """,
                (repository_id.value,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            return RepositoryState(
                repository_id=RepositoryId(row[0]),
                current_commit_sha=CommitSha(row[1]),
                current_branch=row[2],
                status=RepositoryStatus(row[3]),
                twin_state=TwinState(row[4]),
                loaded_components=tuple(json.loads(row[5])),
            )
        except Exception as exc:
            raise StorageError(f"failed to read twin repository state: {exc}") from exc

    def save_state(self, state: RepositoryState) -> None:
        updated_at = datetime.now(timezone.utc).isoformat()
        conn = self._connections.connection()
        try:
            conn.execute(
                """
                INSERT INTO ria_twin_state
                (repository_id, current_commit_sha, current_branch, status, twin_state, loaded_components_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(repository_id) DO UPDATE SET
                    current_commit_sha = excluded.current_commit_sha,
                    current_branch = excluded.current_branch,
                    status = excluded.status,
                    twin_state = excluded.twin_state,
                    loaded_components_json = excluded.loaded_components_json,
                    updated_at = excluded.updated_at
                """,
                (
                    state.repository_id.value,
                    state.current_commit_sha.value,
                    state.current_branch,
                    state.status.value,
                    state.twin_state.value,
                    json.dumps(list(state.loaded_components)),
                    updated_at,
                ),
            )
        except Exception as exc:
            raise StorageError(f"failed to save twin repository state: {exc}") from exc


class SqliteTwinStore(TwinStorePort):
    """SQLite implementation of TwinStorePort."""

    def __init__(self, connections: ConnectionProvider) -> None:
        self._connections = connections

    def save_snapshot(self, snapshot: TwinSnapshot) -> None:
        repo_id = (
            str(snapshot.repository_id.value)
            if hasattr(snapshot.repository_id, "value")
            else str(snapshot.repository_id)
        )
        sha = (
            str(snapshot.commit_sha.value)
            if hasattr(snapshot.commit_sha, "value")
            else str(snapshot.commit_sha)
        )
        created_at = datetime.now(timezone.utc).isoformat()

        conn = self._connections.connection()
        try:
            twin_json = json.dumps(_serialize_twin(snapshot.twin), default=str)
            fp_json = json.dumps(
                {
                    "builder_name": snapshot.fingerprint.builder_name,
                    "version": snapshot.fingerprint.version.token(),
                },
                default=str,
            )

            conn.execute(
                """
                INSERT INTO ria_twin_snapshot (repository_id, commit_sha, twin_id, twin_json, fingerprint_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(repository_id, commit_sha) DO UPDATE SET
                    twin_json = excluded.twin_json,
                    fingerprint_json = excluded.fingerprint_json,
                    created_at = excluded.created_at
                """,
                (repo_id, sha, snapshot.twin_id.value, twin_json, fp_json, created_at),
            )
        except Exception as exc:
            raise StorageError(f"failed to save twin snapshot: {exc}") from exc

    def get_snapshot(
        self,
        repository_id: RepositoryId,
        commit_sha: CommitSha,
    ) -> Optional[TwinSnapshot]:
        conn = self._connections.connection()
        try:
            cursor = conn.execute(
                """
                SELECT twin_id, twin_json, fingerprint_json
                FROM ria_twin_snapshot WHERE repository_id = ? AND commit_sha = ?
                """,
                (repository_id.value, commit_sha.value),
            )
            row = cursor.fetchone()
            if not row:
                return None

            tid = TwinId(row[0])
            twin = _deserialize_twin(json.loads(row[1]))
            fp_d = json.loads(row[2])
            fp = TwinFingerprint(builder_name=fp_d.get("builder_name", "twin-builder"))

            return TwinSnapshot(
                twin_id=tid,
                repository_id=repository_id,
                commit_sha=commit_sha,
                twin=twin,
                fingerprint=fp,
            )
        except Exception as exc:
            raise StorageError(f"failed to read twin snapshot: {exc}") from exc


class SqliteTwinCacheStore(TwinCacheStore):
    """SQLite implementation of TwinCacheStore."""

    def __init__(self, connections: ConnectionProvider) -> None:
        self._connections = connections

    def get(self, key: TwinCacheKey) -> Optional[TwinSnapshot]:
        digest = key.digest()
        conn = self._connections.connection()
        try:
            cursor = conn.execute(
                "SELECT snapshot_json FROM ria_twin_cache WHERE cache_key_digest = ?",
                (digest,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return _deserialize_twin_snapshot(json.loads(row[0]))
        except Exception as exc:
            raise StorageError(f"failed to read twin cache entry: {exc}") from exc

    def put(self, key: TwinCacheKey, snapshot: TwinSnapshot) -> None:
        digest = key.digest()
        sha = key.commit_sha.value
        fp_digest = key.fingerprint.digest()
        snapshot_json = json.dumps(_serialize_twin_snapshot(snapshot), default=str)
        cached_at = datetime.now(timezone.utc).isoformat()

        conn = self._connections.connection()
        try:
            conn.execute(
                """
                INSERT INTO ria_twin_cache (cache_key_digest, commit_sha, fingerprint_digest, snapshot_json, cached_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(cache_key_digest) DO UPDATE SET snapshot_json = excluded.snapshot_json, cached_at = excluded.cached_at
                """,
                (digest, sha, fp_digest, snapshot_json, cached_at),
            )
        except Exception as exc:
            raise StorageError(f"failed to write twin cache entry: {exc}") from exc

    def invalidate_by_commit(self, commit_sha: CommitSha) -> int:
        conn = self._connections.connection()
        try:
            cursor = conn.execute(
                "DELETE FROM ria_twin_cache WHERE commit_sha = ?",
                (commit_sha.value,),
            )
            return cursor.rowcount
        except Exception as exc:
            raise StorageError(
                f"failed to invalidate twin cache by commit: {exc}"
            ) from exc

    def clear(self) -> None:
        conn = self._connections.connection()
        try:
            conn.execute("DELETE FROM ria_twin_cache")
        except Exception as exc:
            raise StorageError(f"failed to clear twin cache: {exc}") from exc


# -- Serialization Helpers --------------------------------------------------


def _serialize_twin(twin: RepositoryTwin) -> Dict[str, Any]:
    return {
        "twin_id": twin.twin_id.value,
        "repository_id": twin.repository.repository_id.value,
        "commit_sha": twin.state.current_commit_sha.value,
        "metadata": {
            "repository_id": twin.metadata.repository_id,
            "commit_sha": twin.metadata.commit_sha,
            "builder_version": twin.metadata.builder_version,
            "schema_version": twin.metadata.schema_version,
        },
        "statistics": {
            "files_total": twin.statistics.files_total,
            "modules_total": twin.statistics.modules_total,
            "symbols_total": twin.statistics.symbols_total,
            "nodes_total": twin.statistics.nodes_total,
            "edges_total": twin.statistics.edges_total,
        },
    }


def _deserialize_twin(d: Dict[str, Any]) -> RepositoryTwin:
    repo_id = RepositoryId(d["repository_id"])
    sha = CommitSha(d["commit_sha"])
    now = datetime.now(timezone.utc)
    repo = Repository(
        repository_id=repo_id,
        moniker=Moniker.parse(f"repo:github.com:org/{repo_id.value}"),
        origin_url=f"https://github.com/org/{repo_id.value}.git",
        default_branch="main",
        tenant_id="default",
        registered_at=now,
        updated_at=now,
    )
    state = RepositoryState(repository_id=repo_id, current_commit_sha=sha)
    g_fp = GraphFingerprint("builder", "1.0.0")
    g_meta = GraphMetadata(repo_id.value, sha.value)
    g_stats = GraphStatistics()
    g_snap = GraphSnapshot(repo_id, sha, Graph(), g_fp, g_meta, g_stats)
    metrics = RepositoryMetrics()
    meta_d = d.get("metadata", {})
    meta = TwinMetadata(
        repository_id=meta_d.get("repository_id", repo_id.value),
        commit_sha=meta_d.get("commit_sha", sha.value),
    )
    stats_d = d.get("statistics", {})
    stats = TwinStatistics(
        files_total=stats_d.get("files_total", 0),
        modules_total=stats_d.get("modules_total", 0),
        symbols_total=stats_d.get("symbols_total", 0),
        nodes_total=stats_d.get("nodes_total", 0),
        edges_total=stats_d.get("edges_total", 0),
    )

    return RepositoryTwin(
        twin_id=TwinId(d["twin_id"]),
        repository=repo,
        state=state,
        graph_snapshot=g_snap,
        metrics=metrics,
        metadata=meta,
        statistics=stats,
    )


def _serialize_twin_snapshot(snap: TwinSnapshot) -> Dict[str, Any]:
    return {
        "twin_id": snap.twin_id.value,
        "repository_id": snap.repository_id.value,
        "commit_sha": snap.commit_sha.value,
        "twin": _serialize_twin(snap.twin),
        "builder_name": snap.fingerprint.builder_name,
    }


def _deserialize_twin_snapshot(d: Dict[str, Any]) -> TwinSnapshot:
    repo_id = RepositoryId(d["repository_id"])
    sha = CommitSha(d["commit_sha"])
    tid = TwinId(d["twin_id"])
    twin = _deserialize_twin(d["twin"])
    fp = TwinFingerprint(builder_name=d.get("builder_name", "twin-builder"))

    return TwinSnapshot(
        twin_id=tid,
        repository_id=repo_id,
        commit_sha=sha,
        twin=twin,
        fingerprint=fp,
    )
