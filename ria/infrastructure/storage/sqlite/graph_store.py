"""SQLite implementation of GraphStorePort and GraphCacheStore ports.

Implements persistent graph storage and durable graph caching over SQLite connections.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Dict, Optional

from ria.domain.enums import EdgeKind, NodeKind
from ria.domain.errors import StorageError
from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.graph import Graph
from ria.domain.models.graph_edge import GraphEdge
from ria.domain.models.graph_edge_id import GraphEdgeId
from ria.domain.models.graph_identity import GraphCacheKey, GraphFingerprint
from ria.domain.models.graph_node import GraphNode
from ria.domain.models.graph_node_id import GraphNodeId
from ria.domain.models.graph_result import GraphMetadata, GraphStatistics
from ria.domain.models.graph_snapshot import GraphSnapshot
from ria.domain.models.scope_id import ScopeId
from ria.domain.models.symbol_id import SymbolId
from ria.infrastructure.storage.sqlite.connection import ConnectionProvider
from ria.ports.graph import GraphCacheStore, GraphStorePort

__all__ = ["SqliteGraphStore", "SqliteGraphCacheStore"]


class SqliteGraphStore(GraphStorePort):
    """SQLite implementation of GraphStorePort."""

    def __init__(self, connections: ConnectionProvider) -> None:
        self._connections = connections

    def save_snapshot(self, snapshot: GraphSnapshot) -> None:
        """Persist snapshot, nodes, and edges inside SQLite transaction."""
        repo_id = (
            str(snapshot.repository_id.value)
            if hasattr(snapshot.repository_id, "value")
            else str(snapshot.repository_id)
        )
        commit_sha = (
            str(snapshot.commit_sha.value)
            if hasattr(snapshot.commit_sha, "value")
            else str(snapshot.commit_sha)
        )
        created_at = datetime.now(timezone.utc).isoformat()

        conn = self._connections.connection()
        try:
            # 1. Save Snapshot Metadata & Statistics
            meta_json = json.dumps(
                {
                    "repository_id": str(snapshot.metadata.repository_id),
                    "commit_sha": str(snapshot.metadata.commit_sha),
                    "builder_version": str(snapshot.metadata.builder_version),
                    "schema_version": str(snapshot.metadata.schema_version),
                }
            )
            stats_json = json.dumps(
                {
                    "nodes_total": snapshot.statistics.nodes_total,
                    "edges_total": snapshot.statistics.edges_total,
                }
            )

            conn.execute(
                """
                INSERT INTO ria_graph_snapshot (repository_id, commit_sha, metadata_json, statistics_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(repository_id, commit_sha) DO UPDATE SET
                    metadata_json = excluded.metadata_json,
                    statistics_json = excluded.statistics_json,
                    created_at = excluded.created_at
                """,
                (repo_id, commit_sha, meta_json, stats_json, created_at),
            )

            # 2. Save Nodes
            node_tuples = [
                (
                    repo_id,
                    commit_sha,
                    n.node_id.value,
                    n.kind.value,
                    n.name,
                    n.qualified_name,
                    n.location_path,
                    n.symbol_id.value if n.symbol_id else None,
                    n.scope_id.value if n.scope_id else None,
                    json.dumps(_serialize_node(n), default=str),
                )
                for n in snapshot.graph.nodes
            ]
            conn.executemany(
                """
                INSERT INTO ria_graph_node
                (repository_id, commit_sha, node_id, kind, name, qualified_name, location_path, symbol_id, scope_id, node_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(repository_id, commit_sha, node_id) DO UPDATE SET node_json = excluded.node_json
                """,
                node_tuples,
            )

            # 3. Save Edges
            edge_tuples = [
                (
                    repo_id,
                    commit_sha,
                    e.edge_id.value,
                    e.kind.value,
                    e.source_id.value,
                    e.target_id.value,
                    e.weight,
                    json.dumps(_serialize_edge(e), default=str),
                )
                for e in snapshot.graph.edges
            ]
            conn.executemany(
                """
                INSERT INTO ria_graph_edge
                (repository_id, commit_sha, edge_id, kind, source_id, target_id, weight, edge_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(repository_id, commit_sha, edge_id) DO UPDATE SET edge_json = excluded.edge_json
                """,
                edge_tuples,
            )
        except Exception as exc:
            raise StorageError(f"failed to save graph snapshot: {exc}") from exc

    def get_snapshot(
        self,
        repository_id: RepositoryId,
        commit_sha: CommitSha,
    ) -> Optional[GraphSnapshot]:
        """Retrieve a persisted GraphSnapshot from SQLite."""
        repo_id = repository_id.value
        sha = commit_sha.value
        conn = self._connections.connection()

        try:
            snap_row = conn.execute(
                "SELECT metadata_json, statistics_json FROM ria_graph_snapshot WHERE repository_id = ? AND commit_sha = ?",
                (repo_id, sha),
            ).fetchone()

            if snap_row is None:
                return None

            node_rows = conn.execute(
                "SELECT node_json FROM ria_graph_node WHERE repository_id = ? AND commit_sha = ?",
                (repo_id, sha),
            ).fetchall()

            edge_rows = conn.execute(
                "SELECT edge_json FROM ria_graph_edge WHERE repository_id = ? AND commit_sha = ?",
                (repo_id, sha),
            ).fetchall()

            nodes = tuple(
                _deserialize_node(json.loads(r["node_json"])) for r in node_rows
            )
            edges = tuple(
                _deserialize_edge(json.loads(r["edge_json"])) for r in edge_rows
            )
            graph = Graph(nodes=nodes, edges=edges)

            meta_data = json.loads(snap_row["metadata_json"])
            stats_data = json.loads(snap_row["statistics_json"])

            fp = GraphFingerprint(
                builder_name="sqlite-graph-store",
                builder_version=meta_data.get("builder_version", "1.0.0"),
                schema_version=meta_data.get("schema_version", "1.0.0"),
            )
            metadata = GraphMetadata(repository_id=repo_id, commit_sha=sha)
            statistics = GraphStatistics(
                nodes_total=stats_data.get("nodes_total", len(nodes)),
                edges_total=stats_data.get("edges_total", len(edges)),
            )

            return GraphSnapshot(
                repository_id=repository_id,
                commit_sha=commit_sha,
                graph=graph,
                fingerprint=fp,
                metadata=metadata,
                statistics=statistics,
            )
        except Exception as exc:
            raise StorageError(f"failed to read graph snapshot: {exc}") from exc


class SqliteGraphCacheStore(GraphCacheStore):
    """SQLite implementation of GraphCacheStore."""

    def __init__(self, connections: ConnectionProvider) -> None:
        self._connections = connections

    def get(self, key: GraphCacheKey) -> Optional[GraphSnapshot]:
        digest = key.digest()
        conn = self._connections.connection()
        try:
            row = conn.execute(
                "SELECT snapshot_json FROM ria_graph_cache WHERE cache_key_digest = ?",
                (digest,),
            ).fetchone()
            if row is None:
                return None
            data = json.loads(row["snapshot_json"])
            return _deserialize_snapshot(data)
        except Exception as exc:
            raise StorageError(f"failed to read graph cache entry: {exc}") from exc

    def put(self, key: GraphCacheKey, snapshot: GraphSnapshot) -> None:
        digest = key.digest()
        sha = key.commit_sha.value
        fp_digest = key.fingerprint.digest()
        snapshot_json = json.dumps(_serialize_snapshot(snapshot), default=str)
        cached_at = datetime.now(timezone.utc).isoformat()

        conn = self._connections.connection()
        try:
            conn.execute(
                """
                INSERT INTO ria_graph_cache (cache_key_digest, commit_sha, fingerprint_digest, snapshot_json, cached_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(cache_key_digest) DO UPDATE SET snapshot_json = excluded.snapshot_json, cached_at = excluded.cached_at
                """,
                (digest, sha, fp_digest, snapshot_json, cached_at),
            )
        except Exception as exc:
            raise StorageError(f"failed to write graph cache entry: {exc}") from exc

    def invalidate_by_commit(self, commit_sha: CommitSha) -> int:
        conn = self._connections.connection()
        try:
            cursor = conn.execute(
                "DELETE FROM ria_graph_cache WHERE commit_sha = ?", (commit_sha.value,)
            )
            return cursor.rowcount
        except Exception as exc:
            raise StorageError(
                f"failed to invalidate graph cache by commit: {exc}"
            ) from exc

    def clear(self) -> None:
        conn = self._connections.connection()
        try:
            conn.execute("DELETE FROM ria_graph_cache")
        except Exception as exc:
            raise StorageError(f"failed to clear graph cache: {exc}") from exc


# -- Serialization Helpers -------------------------------------------------


def _serialize_node(n: GraphNode) -> Dict[str, Any]:
    return {
        "node_id": n.node_id.value,
        "kind": n.kind.value,
        "name": n.name,
        "qualified_name": n.qualified_name,
        "location_path": n.location_path,
        "symbol_id": n.symbol_id.value if n.symbol_id else None,
        "scope_id": n.scope_id.value if n.scope_id else None,
        "properties": dict(n.properties),
    }


def _deserialize_node(d: Dict[str, Any]) -> GraphNode:
    return GraphNode(
        node_id=GraphNodeId(d["node_id"]),
        kind=NodeKind(d["kind"]),
        name=d["name"],
        qualified_name=d.get("qualified_name"),
        location_path=d.get("location_path"),
        symbol_id=SymbolId(d["symbol_id"]) if d.get("symbol_id") else None,
        scope_id=ScopeId(d["scope_id"]) if d.get("scope_id") else None,
        properties=d.get("properties", {}),
    )


def _serialize_edge(e: GraphEdge) -> Dict[str, Any]:
    return {
        "edge_id": e.edge_id.value,
        "kind": e.kind.value,
        "source_id": e.source_id.value,
        "target_id": e.target_id.value,
        "weight": e.weight,
        "properties": dict(e.properties),
    }


def _deserialize_edge(d: Dict[str, Any]) -> GraphEdge:
    return GraphEdge(
        edge_id=GraphEdgeId(d["edge_id"]),
        kind=EdgeKind(d["kind"]),
        source_id=GraphNodeId(d["source_id"]),
        target_id=GraphNodeId(d["target_id"]),
        weight=d.get("weight", 1.0),
        properties=d.get("properties", {}),
    )


def _serialize_snapshot(snap: GraphSnapshot) -> Dict[str, Any]:
    return {
        "repository_id": str(snap.repository_id.value)
        if hasattr(snap.repository_id, "value")
        else str(snap.repository_id),
        "commit_sha": str(snap.commit_sha.value)
        if hasattr(snap.commit_sha, "value")
        else str(snap.commit_sha),
        "nodes": [_serialize_node(n) for n in snap.graph.nodes],
        "edges": [_serialize_edge(e) for e in snap.graph.edges],
        "builder_name": snap.fingerprint.builder_name,
        "builder_version": snap.fingerprint.builder_version,
    }


def _deserialize_snapshot(d: Dict[str, Any]) -> GraphSnapshot:
    repo_id = RepositoryId(d["repository_id"])
    sha = CommitSha(d["commit_sha"])
    nodes = tuple(_deserialize_node(n) for n in d.get("nodes", []))
    edges = tuple(_deserialize_edge(e) for e in d.get("edges", []))
    graph = Graph(nodes=nodes, edges=edges)

    fp = GraphFingerprint(
        builder_name=d.get("builder_name", "graph-cache"),
        builder_version=d.get("builder_version", "1.0.0"),
    )
    meta = GraphMetadata(repository_id=repo_id.value, commit_sha=sha.value)
    stats = GraphStatistics(nodes_total=len(nodes), edges_total=len(edges))

    return GraphSnapshot(
        repository_id=repo_id,
        commit_sha=sha,
        graph=graph,
        fingerprint=fp,
        metadata=meta,
        statistics=stats,
    )
