"""Graph domain entity.

Represents an immutable, indexed in-memory Repository Knowledge Graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ria.domain.enums import EdgeKind, NodeKind
from ria.domain.models.graph_edge import GraphEdge
from ria.domain.models.graph_edge_id import GraphEdgeId
from ria.domain.models.graph_node import GraphNode
from ria.domain.models.graph_node_id import GraphNodeId
from ria.domain.models.symbol_id import SymbolId

__all__ = ["Graph"]


@dataclass(frozen=True)
class Graph:
    """Immutable, indexed Repository Knowledge Graph.

    Attributes:
        nodes: Tuple of all GraphNode instances.
        edges: Tuple of all GraphEdge instances.
    """

    nodes: Tuple[GraphNode, ...] = ()
    edges: Tuple[GraphEdge, ...] = ()

    # Pre-computed fast lookup maps
    _node_map: Dict[GraphNodeId, GraphNode] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )
    _edge_map: Dict[GraphEdgeId, GraphEdge] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )
    _outgoing: Dict[GraphNodeId, List[GraphEdge]] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )
    _incoming: Dict[GraphNodeId, List[GraphEdge]] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )
    _symbol_map: Dict[SymbolId, GraphNode] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        node_map: Dict[GraphNodeId, GraphNode] = {}
        symbol_map: Dict[SymbolId, GraphNode] = {}
        for n in self.nodes:
            node_map[n.node_id] = n
            if n.symbol_id is not None:
                symbol_map[n.symbol_id] = n

        edge_map: Dict[GraphEdgeId, GraphEdge] = {}
        outgoing: Dict[GraphNodeId, List[GraphEdge]] = {}
        incoming: Dict[GraphNodeId, List[GraphEdge]] = {}

        for e in self.edges:
            edge_map[e.edge_id] = e
            outgoing.setdefault(e.source_id, []).append(e)
            incoming.setdefault(e.target_id, []).append(e)

        object.__setattr__(self, "_node_map", node_map)
        object.__setattr__(self, "_edge_map", edge_map)
        object.__setattr__(self, "_outgoing", outgoing)
        object.__setattr__(self, "_incoming", incoming)
        object.__setattr__(self, "_symbol_map", symbol_map)

    def get_node(self, node_id: GraphNodeId) -> Optional[GraphNode]:
        """Look up node by GraphNodeId."""
        return self._node_map.get(node_id)

    def get_edge(self, edge_id: GraphEdgeId) -> Optional[GraphEdge]:
        """Look up edge by GraphEdgeId."""
        return self._edge_map.get(edge_id)

    def get_node_by_symbol_id(self, symbol_id: SymbolId) -> Optional[GraphNode]:
        """Look up node bound to SymbolId."""
        return self._symbol_map.get(symbol_id)

    def outgoing_edges(
        self, source_id: GraphNodeId, kind: Optional[EdgeKind] = None
    ) -> Tuple[GraphEdge, ...]:
        """Get outgoing edges from source_id, optionally filtered by EdgeKind."""
        edges = self._outgoing.get(source_id, [])
        if kind is not None:
            return tuple(e for e in edges if e.kind is kind)
        return tuple(edges)

    def incoming_edges(
        self, target_id: GraphNodeId, kind: Optional[EdgeKind] = None
    ) -> Tuple[GraphEdge, ...]:
        """Get incoming edges to target_id, optionally filtered by EdgeKind."""
        edges = self._incoming.get(target_id, [])
        if kind is not None:
            return tuple(e for e in edges if e.kind is kind)
        return tuple(edges)

    def filter_nodes(self, kind: NodeKind) -> Tuple[GraphNode, ...]:
        """Return all nodes of a specific NodeKind."""
        return tuple(n for n in self.nodes if n.kind is kind)

    def filter_edges(self, kind: EdgeKind) -> Tuple[GraphEdge, ...]:
        """Return all edges of a specific EdgeKind."""
        return tuple(e for e in self.edges if e.kind is kind)
