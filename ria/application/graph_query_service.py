"""Graph Query application service.

Provides indexed lookups for nodes, symbols, files, qualified names, relationships, reverse edges, and neighbors.
Implements :class:`~ria.ports.graph.GraphQueryPort`.
"""

from __future__ import annotations

from typing import Optional, Tuple

from ria.domain.enums import EdgeKind
from ria.domain.models.graph import Graph
from ria.domain.models.graph_node import GraphNode
from ria.domain.models.graph_node_id import GraphNodeId
from ria.domain.models.relationship import Relationship
from ria.domain.models.symbol_id import SymbolId
from ria.ports.graph import GraphQueryPort

__all__ = ["GraphQueryService"]


class GraphQueryService(GraphQueryPort):
    """Service for querying graph nodes, relationships, and indexes."""

    def find_node(self, graph: Graph, node_id: GraphNodeId) -> Optional[GraphNode]:
        """Look up a node by node_id."""
        return graph.get_node(node_id)

    def find_symbol_node(
        self, graph: Graph, symbol_id: SymbolId
    ) -> Optional[GraphNode]:
        """Look up a node by bound SymbolId."""
        return graph.get_node_by_symbol_id(symbol_id)

    def find_nodes_by_file(
        self, graph: Graph, location_path: str
    ) -> Tuple[GraphNode, ...]:
        """Look up all nodes defined within location_path."""
        return tuple(n for n in graph.nodes if n.location_path == location_path)

    def find_nodes_by_qualified_name(
        self, graph: Graph, qualified_name: str
    ) -> Tuple[GraphNode, ...]:
        """Look up all nodes matching qualified_name."""
        return tuple(n for n in graph.nodes if n.qualified_name == qualified_name)

    def neighbors(
        self,
        graph: Graph,
        node_id: GraphNodeId,
        edge_kind: Optional[EdgeKind] = None,
    ) -> Tuple[GraphNode, ...]:
        """Return adjacent neighbor nodes."""
        outgoing = graph.outgoing_edges(node_id, kind=edge_kind)
        target_ids = {e.target_id for e in outgoing}
        return tuple(n for n in graph.nodes if n.node_id in target_ids)

    def incoming_relationships(
        self,
        graph: Graph,
        node_id: GraphNodeId,
    ) -> Tuple[Relationship, ...]:
        """Return incoming Relationship tuples."""
        target_node = graph.get_node(node_id)
        if target_node is None:
            return ()

        rels: list[Relationship] = []
        for edge in graph.incoming_edges(node_id):
            source_node = graph.get_node(edge.source_id)
            if source_node is not None:
                rels.append(
                    Relationship(
                        source_node=source_node, edge=edge, target_node=target_node
                    )
                )
        return tuple(rels)

    def outgoing_relationships(
        self,
        graph: Graph,
        node_id: GraphNodeId,
    ) -> Tuple[Relationship, ...]:
        """Return outgoing Relationship tuples."""
        source_node = graph.get_node(node_id)
        if source_node is None:
            return ()

        rels: list[Relationship] = []
        for edge in graph.outgoing_edges(node_id):
            target_node = graph.get_node(edge.target_id)
            if target_node is not None:
                rels.append(
                    Relationship(
                        source_node=source_node, edge=edge, target_node=target_node
                    )
                )
        return tuple(rels)
