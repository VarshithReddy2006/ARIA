"""Unit tests for GraphProjectionService (Phase 5)."""

from __future__ import annotations


from ria.application.graph_projections import GraphProjectionService
from ria.domain.enums import EdgeKind, NodeKind
from ria.domain.models.graph import Graph
from ria.domain.models.graph_edge import GraphEdge
from ria.domain.models.graph_edge_id import GraphEdgeId
from ria.domain.models.graph_node import GraphNode
from ria.domain.models.graph_node_id import GraphNodeId


def test_graph_projections() -> None:
    n1 = GraphNode(node_id=GraphNodeId("n1"), kind=NodeKind.FUNCTION, name="foo")
    n2 = GraphNode(node_id=GraphNodeId("n2"), kind=NodeKind.FUNCTION, name="bar")
    n3 = GraphNode(node_id=GraphNodeId("n3"), kind=NodeKind.FILE, name="app.py")

    e1 = GraphEdge(
        edge_id=GraphEdgeId("e1"),
        kind=EdgeKind.CALLS,
        source_id=n1.node_id,
        target_id=n2.node_id,
    )
    e2 = GraphEdge(
        edge_id=GraphEdgeId("e2"),
        kind=EdgeKind.CONTAINS,
        source_id=n3.node_id,
        target_id=n1.node_id,
    )

    master = Graph(nodes=(n1, n2, n3), edges=(e1, e2))
    proj_svc = GraphProjectionService()

    call_graph = proj_svc.project_call_graph(master)
    assert len(call_graph.nodes) == 2
    assert len(call_graph.edges) == 1
    assert call_graph.edges[0].kind is EdgeKind.CALLS

    import_graph = proj_svc.project_import_graph(master)
    assert len(import_graph.nodes) == 1
    assert len(import_graph.edges) == 0
