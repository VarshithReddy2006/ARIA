"""Graph Traversal application service.

Implements deterministic BFS, DFS, Shortest Path, Reachability, Ancestor, Descendant, and Subgraph traversals.
Implements :class:`~ria.ports.graph.TraversalPort`.
"""

from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional, Set, Tuple

from ria.domain.enums import EdgeKind
from ria.domain.models.graph import Graph
from ria.domain.models.graph_edge import GraphEdge
from ria.domain.models.graph_node import GraphNode
from ria.domain.models.graph_node_id import GraphNodeId
from ria.domain.models.graph_result import TraversalResult
from ria.ports.graph import TraversalPort

__all__ = ["GraphTraversalService"]


class GraphTraversalService(TraversalPort):
    """Service for deterministic graph traversal algorithms."""

    def breadth_first(
        self,
        graph: Graph,
        start_id: GraphNodeId,
        max_depth: Optional[int] = None,
    ) -> TraversalResult:
        """Execute deterministic Breadth-First Search (BFS) starting from start_id."""
        start_node = graph.get_node(start_id)
        if start_node is None:
            return TraversalResult()

        visited_nodes: List[GraphNode] = []
        traversed_edges: List[GraphEdge] = []
        visited_ids: Set[GraphNodeId] = set()

        queue: deque[Tuple[GraphNode, int]] = deque([(start_node, 0)])
        visited_ids.add(start_id)

        while queue:
            node, depth = queue.popleft()
            visited_nodes.append(node)

            if max_depth is not None and depth >= max_depth:
                continue

            for edge in graph.outgoing_edges(node.node_id):
                target_node = graph.get_node(edge.target_id)
                if target_node is not None and target_node.node_id not in visited_ids:
                    visited_ids.add(target_node.node_id)
                    traversed_edges.append(edge)
                    queue.append((target_node, depth + 1))

        return TraversalResult(
            visited_nodes=tuple(visited_nodes),
            traversed_edges=tuple(traversed_edges),
            path_length=len(traversed_edges),
            reachability_score=1.0 if visited_nodes else 0.0,
        )

    def depth_first(
        self,
        graph: Graph,
        start_id: GraphNodeId,
        max_depth: Optional[int] = None,
    ) -> TraversalResult:
        """Execute deterministic Depth-First Search (DFS) starting from start_id."""
        start_node = graph.get_node(start_id)
        if start_node is None:
            return TraversalResult()

        visited_nodes: List[GraphNode] = []
        traversed_edges: List[GraphEdge] = []
        visited_ids: Set[GraphNodeId] = set()

        def _dfs(node: GraphNode, depth: int) -> None:
            visited_ids.add(node.node_id)
            visited_nodes.append(node)

            if max_depth is not None and depth >= max_depth:
                return

            for edge in graph.outgoing_edges(node.node_id):
                target_node = graph.get_node(edge.target_id)
                if target_node is not None and target_node.node_id not in visited_ids:
                    traversed_edges.append(edge)
                    _dfs(target_node, depth + 1)

        _dfs(start_node, 0)

        return TraversalResult(
            visited_nodes=tuple(visited_nodes),
            traversed_edges=tuple(traversed_edges),
            path_length=len(traversed_edges),
            reachability_score=1.0 if visited_nodes else 0.0,
        )

    def shortest_path(
        self,
        graph: Graph,
        start_id: GraphNodeId,
        target_id: GraphNodeId,
    ) -> TraversalResult:
        """Compute shortest path (unweighted BFS) between start_id and target_id."""
        start_node = graph.get_node(start_id)
        target_node = graph.get_node(target_id)

        if start_node is None or target_node is None:
            return TraversalResult(reachability_score=0.0)

        if start_id == target_id:
            return TraversalResult(
                visited_nodes=(start_node,), path_length=0, reachability_score=1.0
            )

        # BFS tracking predecessors
        parent_map: Dict[GraphNodeId, Tuple[GraphNode, GraphEdge]] = {}
        queue: deque[GraphNode] = deque([start_node])
        visited: Set[GraphNodeId] = {start_id}

        found = False
        while queue:
            curr = queue.popleft()
            if curr.node_id == target_id:
                found = True
                break

            for edge in graph.outgoing_edges(curr.node_id):
                nxt = graph.get_node(edge.target_id)
                if nxt is not None and nxt.node_id not in visited:
                    visited.add(nxt.node_id)
                    parent_map[nxt.node_id] = (curr, edge)
                    queue.append(nxt)

        if not found:
            return TraversalResult(reachability_score=0.0)

        # Reconstruct path
        path_nodes: List[GraphNode] = [target_node]
        path_edges: List[GraphEdge] = []
        curr_id = target_id

        while curr_id != start_id:
            parent_node, edge = parent_map[curr_id]
            path_nodes.append(parent_node)
            path_edges.append(edge)
            curr_id = parent_node.node_id

        path_nodes.reverse()
        path_edges.reverse()

        return TraversalResult(
            visited_nodes=tuple(path_nodes),
            traversed_edges=tuple(path_edges),
            path_length=len(path_edges),
            reachability_score=1.0,
        )

    def reachability(
        self,
        graph: Graph,
        start_id: GraphNodeId,
        target_id: GraphNodeId,
    ) -> bool:
        """Check if target_id is reachable from start_id."""
        res = self.shortest_path(graph, start_id, target_id)
        return res.reachability_score > 0.0

    def ancestors(
        self,
        graph: Graph,
        node_id: GraphNodeId,
        edge_kind: Optional[EdgeKind] = None,
    ) -> Tuple[GraphNode, ...]:
        """Find all upstream ancestor nodes following incoming edges."""
        visited: List[GraphNode] = []
        visited_ids: Set[GraphNodeId] = {node_id}
        queue: deque[GraphNodeId] = deque([node_id])

        while queue:
            curr_id = queue.popleft()
            for edge in graph.incoming_edges(curr_id, kind=edge_kind):
                source_node = graph.get_node(edge.source_id)
                if source_node is not None and source_node.node_id not in visited_ids:
                    visited_ids.add(source_node.node_id)
                    visited.append(source_node)
                    queue.append(source_node.node_id)

        return tuple(visited)

    def descendants(
        self,
        graph: Graph,
        node_id: GraphNodeId,
        edge_kind: Optional[EdgeKind] = None,
    ) -> Tuple[GraphNode, ...]:
        """Find all downstream descendant nodes following outgoing edges."""
        visited: List[GraphNode] = []
        visited_ids: Set[GraphNodeId] = {node_id}
        queue: deque[GraphNodeId] = deque([node_id])

        while queue:
            curr_id = queue.popleft()
            for edge in graph.outgoing_edges(curr_id, kind=edge_kind):
                target_node = graph.get_node(edge.target_id)
                if target_node is not None and target_node.node_id not in visited_ids:
                    visited_ids.add(target_node.node_id)
                    visited.append(target_node)
                    queue.append(target_node.node_id)

        return tuple(visited)
