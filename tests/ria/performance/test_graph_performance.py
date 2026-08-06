"""Performance benchmarks for Milestone 5 — Repository Knowledge Graph (Phase 13)."""

from __future__ import annotations

import time

from ria.application.graph_traversal_service import GraphTraversalService
from ria.domain.enums import EdgeKind, NodeKind
from ria.domain.models.graph import Graph
from ria.domain.models.graph_edge import GraphEdge
from ria.domain.models.graph_edge_id import GraphEdgeId
from ria.domain.models.graph_node import GraphNode
from ria.domain.models.graph_node_id import GraphNodeId
from ria.domain.models.scope_id import ScopeId
from ria.domain.models.span import SourcePosition, SourceSpan
from ria.domain.models.symbol_id import SymbolId


def test_graph_performance_benchmarks() -> None:
    pos = SourcePosition(0, 0, 0)
    span = SourceSpan(pos, pos)

    # Generate 500 nodes and edges
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    scope_id = ScopeId.root("python", "app.py")

    t0 = time.perf_counter()
    for i in range(500):
        sym_id = SymbolId.for_symbol("python", f"src/mod_{i}.py", f"fn_{i}", span)
        node = GraphNode(
            node_id=GraphNodeId(f"n_{i}"),
            kind=NodeKind.FUNCTION,
            name=f"fn_{i}",
            symbol_id=sym_id,
            scope_id=scope_id,
        )
        nodes.append(node)

    t_nodes = time.perf_counter() - t0

    for i in range(499):
        e = GraphEdge(
            edge_id=GraphEdgeId(f"e_{i}"),
            kind=EdgeKind.CALLS,
            source_id=nodes[i].node_id,
            target_id=nodes[i + 1].node_id,
        )
        edges.append(e)

    t0 = time.perf_counter()
    graph = Graph(nodes=tuple(nodes), edges=tuple(edges))
    t_graph_init = time.perf_counter() - t0

    # Test Traversal Performance
    traversal_svc = GraphTraversalService()
    t0 = time.perf_counter()
    res = traversal_svc.breadth_first(graph, nodes[0].node_id)
    t_bfs = time.perf_counter() - t0

    assert len(res.visited_nodes) == 500
    assert t_nodes < 0.5  # Node creation < 500ms
    assert t_graph_init < 0.1  # Graph indexing < 100ms
    assert t_bfs < 0.05  # BFS 500 nodes < 50ms
