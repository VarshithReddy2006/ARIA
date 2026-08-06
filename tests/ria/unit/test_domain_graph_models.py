"""Unit tests for Milestone 5 Phase 1 Graph Domain Models."""

from __future__ import annotations

import pytest

from ria.domain.enums import DiagnosticSeverity, EdgeKind, NodeKind
from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.graph import Graph
from ria.domain.models.graph_edge import GraphEdge
from ria.domain.models.graph_edge_id import GraphEdgeId
from ria.domain.models.graph_identity import GraphCacheKey, GraphFingerprint
from ria.domain.models.graph_node import GraphNode
from ria.domain.models.graph_node_id import GraphNodeId
from ria.domain.models.graph_result import (
    GraphDiagnostic,
    GraphMetadata,
    GraphStatistics,
    TraversalResult,
)
from ria.domain.models.graph_snapshot import GraphSnapshot
from ria.domain.models.relationship import Relationship


def test_graph_node_id_invariants() -> None:
    nid1 = GraphNodeId.for_node(NodeKind.FUNCTION, "repo1", "src/math.py::calc")
    nid2 = GraphNodeId.for_node(NodeKind.FUNCTION, "repo1", "src/math.py::calc")
    nid3 = GraphNodeId.for_node(NodeKind.CLASS, "repo1", "src/math.py::CalcClass")

    assert nid1 == nid2
    assert nid1 != nid3
    assert str(nid1) == nid1.value

    with pytest.raises(ValueError, match="non-empty string"):
        GraphNodeId("")


def test_graph_edge_id_invariants() -> None:
    n1 = GraphNodeId.for_node(NodeKind.FILE, "repo1", "src/a.py")
    n2 = GraphNodeId.for_node(NodeKind.FUNCTION, "repo1", "src/a.py::foo")

    e1 = GraphEdgeId.for_edge(EdgeKind.CONTAINS, n1, n2)
    e2 = GraphEdgeId.for_edge(EdgeKind.CONTAINS, n1, n2)

    assert e1 == e2
    assert str(e1) == e1.value

    with pytest.raises(ValueError, match="non-empty string"):
        GraphEdgeId("   ")


def test_graph_node_invariants() -> None:
    nid = GraphNodeId.for_node(NodeKind.FUNCTION, "repo1", "src/app.py::main")
    node = GraphNode(node_id=nid, kind=NodeKind.FUNCTION, name="main")

    assert node.node_id == nid
    assert node.kind is NodeKind.FUNCTION
    assert node.name == "main"

    with pytest.raises(ValueError, match="non-empty string"):
        GraphNode(node_id=nid, kind=NodeKind.FUNCTION, name="")


def test_graph_edge_invariants() -> None:
    n1 = GraphNodeId.for_node(NodeKind.FUNCTION, "repo1", "src/a.py::foo")
    n2 = GraphNodeId.for_node(NodeKind.FUNCTION, "repo1", "src/b.py::bar")
    eid = GraphEdgeId.for_edge(EdgeKind.CALLS, n1, n2)

    edge = GraphEdge(
        edge_id=eid, kind=EdgeKind.CALLS, source_id=n1, target_id=n2, weight=2.5
    )

    assert edge.edge_id == eid
    assert edge.weight == 2.5

    with pytest.raises(ValueError, match="non-negative"):
        GraphEdge(
            edge_id=eid, kind=EdgeKind.CALLS, source_id=n1, target_id=n2, weight=-1.0
        )


def test_relationship_invariants() -> None:
    n1_id = GraphNodeId.for_node(NodeKind.CLASS, "repo1", "Animal")
    n2_id = GraphNodeId.for_node(NodeKind.CLASS, "repo1", "Dog")

    n1 = GraphNode(node_id=n1_id, kind=NodeKind.CLASS, name="Animal")
    n2 = GraphNode(node_id=n2_id, kind=NodeKind.CLASS, name="Dog")

    eid = GraphEdgeId.for_edge(EdgeKind.EXTENDS, n2_id, n1_id)
    edge = GraphEdge(
        edge_id=eid, kind=EdgeKind.EXTENDS, source_id=n2_id, target_id=n1_id
    )

    rel = Relationship(source_node=n2, edge=edge, target_node=n1)
    assert rel.source_node == n2
    assert rel.target_node == n1

    # Mismatched source failure
    with pytest.raises(ValueError, match="source_id"):
        Relationship(source_node=n1, edge=edge, target_node=n1)


def test_graph_query_and_indexing() -> None:
    n1_id = GraphNodeId.for_node(NodeKind.FILE, "repo1", "src/app.py")
    n2_id = GraphNodeId.for_node(NodeKind.FUNCTION, "repo1", "src/app.py::main")
    n1 = GraphNode(node_id=n1_id, kind=NodeKind.FILE, name="app.py")
    n2 = GraphNode(node_id=n2_id, kind=NodeKind.FUNCTION, name="main")

    eid = GraphEdgeId.for_edge(EdgeKind.CONTAINS, n1_id, n2_id)
    edge = GraphEdge(
        edge_id=eid, kind=EdgeKind.CONTAINS, source_id=n1_id, target_id=n2_id
    )

    graph = Graph(nodes=(n1, n2), edges=(edge,))

    assert graph.get_node(n1_id) == n1
    assert graph.get_edge(eid) == edge
    assert graph.outgoing_edges(n1_id) == (edge,)
    assert graph.incoming_edges(n2_id) == (edge,)
    assert graph.filter_nodes(NodeKind.FILE) == (n1,)
    assert graph.filter_edges(EdgeKind.CONTAINS) == (edge,)


def test_graph_identity_and_snapshot() -> None:
    fp = GraphFingerprint(builder_name="test-builder", builder_version="1.0.0")
    key = GraphCacheKey(commit_sha=CommitSha("a" * 40), fingerprint=fp)

    assert key.reuse_key == "a" * 40
    assert key.digest() is not None

    meta = GraphMetadata(repository_id="repo1", commit_sha="a" * 40)
    stats = GraphStatistics(nodes_total=2, edges_total=1)
    graph = Graph()

    snapshot = GraphSnapshot(
        repository_id=RepositoryId("repo1"),
        commit_sha=CommitSha("a" * 40),
        graph=graph,
        fingerprint=fp,
        metadata=meta,
        statistics=stats,
    )

    assert snapshot.repository_id == RepositoryId("repo1")
    assert snapshot.statistics.nodes_total == 2


def test_traversal_result_and_diagnostics() -> None:
    diag = GraphDiagnostic(
        severity=DiagnosticSeverity.WARNING, message="Orphan node detected"
    )
    assert diag.severity is DiagnosticSeverity.WARNING

    res = TraversalResult(visited_nodes=(), traversed_edges=(), path_length=0)
    assert res.path_length == 0
