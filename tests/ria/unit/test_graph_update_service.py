"""Unit tests for GraphUpdateService (Phase 6)."""

from __future__ import annotations


from ria.application.graph_update_service import GraphUpdateService
from ria.domain.enums import EdgeKind, NodeKind
from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.change_set import ChangeSet
from ria.domain.models.graph import Graph
from ria.domain.models.graph_edge import GraphEdge
from ria.domain.models.graph_edge_id import GraphEdgeId
from ria.domain.models.graph_identity import GraphFingerprint
from ria.domain.models.graph_node import GraphNode
from ria.domain.models.graph_node_id import GraphNodeId
from ria.domain.models.graph_result import GraphMetadata, GraphStatistics
from ria.domain.models.graph_snapshot import GraphSnapshot


def test_incremental_update() -> None:
    repo_id = RepositoryId("repo1")
    commit_1 = CommitSha("1" * 40)
    commit_2 = CommitSha("2" * 40)

    n1 = GraphNode(
        node_id=GraphNodeId("n1"), kind=NodeKind.FILE, name="a.py", location_path="a.py"
    )
    n2 = GraphNode(
        node_id=GraphNodeId("n2"), kind=NodeKind.FILE, name="b.py", location_path="b.py"
    )
    e1 = GraphEdge(
        edge_id=GraphEdgeId("e1"),
        kind=EdgeKind.CALLS,
        source_id=n1.node_id,
        target_id=n2.node_id,
    )

    g1 = Graph(nodes=(n1, n2), edges=(e1,))
    fp = GraphFingerprint("builder", "1.0.0")
    meta = GraphMetadata("repo1", commit_1.value)
    stats = GraphStatistics(nodes_total=2, edges_total=1)
    snap1 = GraphSnapshot(repo_id, commit_1, g1, fp, meta, stats)

    # ChangeSet: delete b.py, add c.py
    cs = ChangeSet(
        head_sha=commit_2.value,
        base_sha=commit_1.value,
        deleted=frozenset({"b.py"}),
        added=frozenset({"c.py"}),
    )
    n3 = GraphNode(
        node_id=GraphNodeId("n3"), kind=NodeKind.FILE, name="c.py", location_path="c.py"
    )

    svc = GraphUpdateService()
    snap2 = svc.incremental_update(snap1, commit_2, cs, new_nodes=(n3,), new_edges=())

    assert len(snap2.graph.nodes) == 2  # a.py and c.py
    node_names = {n.name for n in snap2.graph.nodes}
    assert node_names == {"a.py", "c.py"}
    assert len(snap2.graph.edges) == 0  # e1 removed because n2 was deleted
