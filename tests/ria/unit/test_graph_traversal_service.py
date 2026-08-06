"""Unit tests for GraphTraversalService (Phase 9)."""

from __future__ import annotations


from ria.application.graph_traversal_service import GraphTraversalService
from ria.domain.enums import EdgeKind, NodeKind
from ria.domain.models.graph import Graph
from ria.domain.models.graph_edge import GraphEdge
from ria.domain.models.graph_edge_id import GraphEdgeId
from ria.domain.models.graph_node import GraphNode
from ria.domain.models.graph_node_id import GraphNodeId


def test_bfs_dfs_and_shortest_path() -> None:
    n1 = GraphNode(node_id=GraphNodeId("n1"), kind=NodeKind.FUNCTION, name="A")
    n2 = GraphNode(node_id=GraphNodeId("n2"), kind=NodeKind.FUNCTION, name="B")
    n3 = GraphNode(node_id=GraphNodeId("n3"), kind=NodeKind.FUNCTION, name="C")

    e1 = GraphEdge(
        edge_id=GraphEdgeId("e1"),
        kind=EdgeKind.CALLS,
        source_id=n1.node_id,
        target_id=n2.node_id,
    )
    e2 = GraphEdge(
        edge_id=GraphEdgeId("e2"),
        kind=EdgeKind.CALLS,
        source_id=n2.node_id,
        target_id=n3.node_id,
    )

    graph = Graph(nodes=(n1, n2, n3), edges=(e1, e2))
    svc = GraphTraversalService()

    bfs_res = svc.breadth_first(graph, n1.node_id)
    assert len(bfs_res.visited_nodes) == 3
    assert bfs_res.visited_nodes == (n1, n2, n3)

    dfs_res = svc.depth_first(graph, n1.node_id)
    assert len(dfs_res.visited_nodes) == 3

    path_res = svc.shortest_path(graph, n1.node_id, n3.node_id)
    assert path_res.reachability_score == 1.0
    assert path_res.path_length == 2
    assert path_res.visited_nodes == (n1, n2, n3)

    assert svc.reachability(graph, n1.node_id, n3.node_id)
    assert not svc.reachability(graph, n3.node_id, n1.node_id)

    descendants = svc.descendants(graph, n1.node_id)
    assert descendants == (n2, n3)

    ancestors = svc.ancestors(graph, n3.node_id)
    assert ancestors == (n2, n1)
