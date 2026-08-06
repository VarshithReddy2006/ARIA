"""Integration tests for SqliteGraphStore and SqliteGraphCacheStore (Phase 7 & 12)."""

from __future__ import annotations

from ria.domain.enums import EdgeKind, NodeKind
from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.graph import Graph
from ria.domain.models.graph_edge import GraphEdge
from ria.domain.models.graph_edge_id import GraphEdgeId
from ria.domain.models.graph_identity import GraphCacheKey, GraphFingerprint
from ria.domain.models.graph_node import GraphNode
from ria.domain.models.graph_node_id import GraphNodeId
from ria.domain.models.graph_result import GraphMetadata, GraphStatistics
from ria.domain.models.graph_snapshot import GraphSnapshot
from ria.infrastructure.storage.sqlite.connection import ConnectionProvider
from ria.infrastructure.storage.sqlite.graph_store import (
    SqliteGraphCacheStore,
    SqliteGraphStore,
)
from ria.infrastructure.storage.sqlite.migrations import MigrationRunner


def test_sqlite_graph_store_and_cache(tmp_path) -> None:
    db_path = tmp_path / "ria_graph.db"
    connections = ConnectionProvider(db_path)
    MigrationRunner(connections).run()

    store = SqliteGraphStore(connections)
    cache_store = SqliteGraphCacheStore(connections)

    repo_id = RepositoryId("repo1")
    commit_sha = CommitSha("a" * 40)

    n1 = GraphNode(node_id=GraphNodeId("n1"), kind=NodeKind.FILE, name="app.py")
    n2 = GraphNode(node_id=GraphNodeId("n2"), kind=NodeKind.FUNCTION, name="main")
    e1 = GraphEdge(
        edge_id=GraphEdgeId("e1"),
        kind=EdgeKind.CONTAINS,
        source_id=n1.node_id,
        target_id=n2.node_id,
    )

    graph = Graph(nodes=(n1, n2), edges=(e1,))
    fp = GraphFingerprint("builder", "1.0.0")
    meta = GraphMetadata("repo1", commit_sha.value)
    stats = GraphStatistics(nodes_total=2, edges_total=1)
    snapshot = GraphSnapshot(repo_id, commit_sha, graph, fp, meta, stats)

    # 1. Save and retrieve snapshot
    store.save_snapshot(snapshot)
    retrieved = store.get_snapshot(repo_id, commit_sha)
    assert retrieved is not None
    assert len(retrieved.graph.nodes) == 2
    assert len(retrieved.graph.edges) == 1

    # 2. Put and get cache entry
    key = GraphCacheKey(commit_sha, fp)
    cache_store.put(key, snapshot)
    cached = cache_store.get(key)
    assert cached is not None
    assert len(cached.graph.nodes) == 2

    # 3. Invalidate cache
    purged = cache_store.invalidate_by_commit(commit_sha)
    assert purged == 1
    assert cache_store.get(key) is None

    connections.close()
