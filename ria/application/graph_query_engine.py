"""Twin Graph Query Engine application service.

Implements deterministic graph queries on a RepositoryTwin's Knowledge Graph snapshot.
Implements :class:`~ria.ports.query.GraphQueryPort`.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from ria.application.graph_query_service import GraphQueryService
from ria.application.graph_traversal_service import GraphTraversalService
from ria.domain.models.graph_node_id import GraphNodeId
from ria.domain.models.query_result import QueryMatch
from ria.domain.models.repository_twin import RepositoryTwin
from ria.ports.query import GraphQueryPort as QueryGraphQueryPort

__all__ = ["TwinGraphQueryEngine"]


class TwinGraphQueryEngine(QueryGraphQueryPort):
    """Engine for deterministic graph queries on a RepositoryTwin."""

    def __init__(
        self,
        query_service: Optional[GraphQueryService] = None,
        traversal_service: Optional[GraphTraversalService] = None,
    ) -> None:
        self._query_svc = query_service or GraphQueryService()
        self._traversal_svc = traversal_service or GraphTraversalService()

    def node_lookup(self, twin: RepositoryTwin, node_id: str) -> Optional[QueryMatch]:
        """Look up a single graph node by node_id."""
        graph = twin.graph_snapshot.graph
        node = graph.get_node(GraphNodeId(node_id))
        if node is None:
            return None
        return QueryMatch(
            id=node.node_id.value,
            kind=node.kind.value,
            name=node.name,
            qualified_name=node.qualified_name,
            location_path=node.location_path,
        )

    def edge_lookup(self, twin: RepositoryTwin, edge_id: str) -> Optional[QueryMatch]:
        """Look up a single graph edge by edge_id."""
        graph = twin.graph_snapshot.graph
        for e in graph.edges:
            if e.edge_id.value == edge_id:
                return QueryMatch(
                    id=e.edge_id.value,
                    kind=e.kind.value,
                    name=f"{e.source_id.value} -> {e.target_id.value}",
                    qualified_name=f"{e.kind.value}:{e.source_id.value}->{e.target_id.value}",
                )
        return None

    def neighbour_lookup(
        self, twin: RepositoryTwin, node_id: str
    ) -> Tuple[QueryMatch, ...]:
        """Look up neighboring nodes."""
        graph = twin.graph_snapshot.graph
        neighbours = self._query_svc.neighbors(graph, GraphNodeId(node_id))
        return tuple(
            QueryMatch(
                id=n.node_id.value,
                kind=n.kind.value,
                name=n.name,
                qualified_name=n.qualified_name,
                location_path=n.location_path,
            )
            for n in neighbours
        )

    def shortest_path(
        self, twin: RepositoryTwin, source_id: str, target_id: str
    ) -> Tuple[QueryMatch, ...]:
        """Find shortest path between source and target nodes."""
        graph = twin.graph_snapshot.graph
        res = self._traversal_svc.shortest_path(
            graph, GraphNodeId(source_id), GraphNodeId(target_id)
        )
        matches: List[QueryMatch] = []
        for nid in res.visited_nodes:
            n = graph.get_node(nid)
            if n is not None:
                matches.append(
                    QueryMatch(
                        id=n.node_id.value,
                        kind=n.kind.value,
                        name=n.name,
                        qualified_name=n.qualified_name,
                        location_path=n.location_path,
                    )
                )
        return tuple(matches)

    def reachability(
        self, twin: RepositoryTwin, source_id: str
    ) -> Tuple[QueryMatch, ...]:
        """Compute set of reachable nodes from source_id."""
        graph = twin.graph_snapshot.graph
        res = self._traversal_svc.breadth_first(graph, GraphNodeId(source_id))
        matches: List[QueryMatch] = []
        for nid in res.visited_nodes:
            n = graph.get_node(nid)
            if n is not None:
                matches.append(
                    QueryMatch(
                        id=n.node_id.value,
                        kind=n.kind.value,
                        name=n.name,
                        qualified_name=n.qualified_name,
                        location_path=n.location_path,
                    )
                )
        return tuple(matches)

    def ancestors(self, twin: RepositoryTwin, node_id: str) -> Tuple[QueryMatch, ...]:
        """Look up ancestor nodes."""
        graph = twin.graph_snapshot.graph
        res = self._traversal_svc.ancestors(graph, GraphNodeId(node_id))
        matches: List[QueryMatch] = []
        for nid in res.visited_nodes:
            n = graph.get_node(nid)
            if n is not None:
                matches.append(
                    QueryMatch(
                        id=n.node_id.value,
                        kind=n.kind.value,
                        name=n.name,
                        qualified_name=n.qualified_name,
                        location_path=n.location_path,
                    )
                )
        return tuple(matches)

    def descendants(self, twin: RepositoryTwin, node_id: str) -> Tuple[QueryMatch, ...]:
        """Look up descendant nodes."""
        graph = twin.graph_snapshot.graph
        res = self._traversal_svc.descendants(graph, GraphNodeId(node_id))
        matches: List[QueryMatch] = []
        for nid in res.visited_nodes:
            n = graph.get_node(nid)
            if n is not None:
                matches.append(
                    QueryMatch(
                        id=n.node_id.value,
                        kind=n.kind.value,
                        name=n.name,
                        qualified_name=n.qualified_name,
                        location_path=n.location_path,
                    )
                )
        return tuple(matches)
