"""Unit tests for GraphQueryService (Phase 8)."""

from __future__ import annotations


from ria.application.graph_query_service import GraphQueryService
from ria.domain.enums import EdgeKind, NodeKind
from ria.domain.models.graph import Graph
from ria.domain.models.graph_edge import GraphEdge
from ria.domain.models.graph_edge_id import GraphEdgeId
from ria.domain.models.graph_node import GraphNode
from ria.domain.models.graph_node_id import GraphNodeId


def test_graph_query_service() -> None:
    n1 = GraphNode(
        node_id=GraphNodeId("n1"),
        kind=NodeKind.FILE,
        name="app.py",
        location_path="src/app.py",
        qualified_name="app",
    )
    n2 = GraphNode(
        node_id=GraphNodeId("n2"),
        kind=NodeKind.FUNCTION,
        name="main",
        location_path="src/app.py",
        qualified_name="app.main",
    )
    e1 = GraphEdge(
        edge_id=GraphEdgeId("e1"),
        kind=EdgeKind.CONTAINS,
        source_id=n1.node_id,
        target_id=n2.node_id,
    )

    graph = Graph(nodes=(n1, n2), edges=(e1,))
    svc = GraphQueryService()

    assert svc.find_node(graph, n1.node_id) == n1
    assert len(svc.find_nodes_by_file(graph, "src/app.py")) == 2
    assert len(svc.find_nodes_by_qualified_name(graph, "app.main")) == 1
    assert svc.neighbors(graph, n1.node_id) == (n2,)

    out_rels = svc.outgoing_relationships(graph, n1.node_id)
    assert len(out_rels) == 1
    assert out_rels[0].source_node == n1
    assert out_rels[0].target_node == n2

    in_rels = svc.incoming_relationships(graph, n2.node_id)
    assert len(in_rels) == 1
    assert in_rels[0].source_node == n1
