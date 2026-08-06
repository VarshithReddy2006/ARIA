"""Relationship domain tuple entity.

Represents a semantic relationship tuple (source_node, edge, target_node).
"""

from __future__ import annotations

from dataclasses import dataclass

from ria.domain.models.graph_edge import GraphEdge
from ria.domain.models.graph_node import GraphNode

__all__ = ["Relationship"]


@dataclass(frozen=True)
class Relationship:
    """Immutable semantic relationship tuple.

    Attributes:
        source_node: Origin GraphNode.
        edge: Directed GraphEdge connecting source to target.
        target_node: Destination GraphNode.
    """

    source_node: GraphNode
    edge: GraphEdge
    target_node: GraphNode

    def __post_init__(self) -> None:
        if self.edge.source_id != self.source_node.node_id:
            raise ValueError(
                f"Relationship edge source_id ({self.edge.source_id}) does not match "
                f"source_node.node_id ({self.source_node.node_id})"
            )
        if self.edge.target_id != self.target_node.node_id:
            raise ValueError(
                f"Relationship edge target_id ({self.edge.target_id}) does not match "
                f"target_node.node_id ({self.target_node.node_id})"
            )
