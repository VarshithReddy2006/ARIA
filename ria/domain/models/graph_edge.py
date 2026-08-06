"""GraphEdge domain entity.

Represents a directed edge connecting two nodes in the Repository Knowledge Graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ria.domain.enums import EdgeKind
from ria.domain.models.graph_edge_id import GraphEdgeId
from ria.domain.models.graph_node_id import GraphNodeId

__all__ = ["GraphEdge"]


@dataclass(frozen=True)
class GraphEdge:
    """Immutable directed edge in the Repository Knowledge Graph.

    Attributes:
        edge_id: Unique GraphEdgeId.
        kind: EdgeKind classification.
        source_id: Origin GraphNodeId.
        target_id: Destination GraphNodeId.
        weight: Non-negative weight of the relationship.
        properties: Immutable mapping of additional edge properties.
    """

    edge_id: GraphEdgeId
    kind: EdgeKind
    source_id: GraphNodeId
    target_id: GraphNodeId
    weight: float = 1.0
    properties: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.weight < 0:
            raise ValueError(
                f"GraphEdge weight must be non-negative, got {self.weight}"
            )
