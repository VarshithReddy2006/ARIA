"""GraphEdgeId value object.

Identifies a directed edge within the Repository Knowledge Graph.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib

from ria.domain.enums import EdgeKind
from ria.domain.models.graph_node_id import GraphNodeId

__all__ = ["GraphEdgeId"]


@dataclass(frozen=True)
class GraphEdgeId:
    """Opaque, immutable identifier for a GraphEdge.

    Attributes:
        value: Non-empty string key.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("GraphEdgeId value must be a non-empty string")

    @classmethod
    def for_edge(
        cls,
        kind: EdgeKind,
        source_id: GraphNodeId,
        target_id: GraphNodeId,
    ) -> GraphEdgeId:
        """Construct a deterministic GraphEdgeId for an edge kind and endpoints.

        Args:
            kind: EdgeKind classification.
            source_id: Origin GraphNodeId.
            target_id: Destination GraphNodeId.

        Returns:
            Deterministic GraphEdgeId.
        """
        raw_key = f"edge:{kind.value}:{source_id.value}:{target_id.value}"
        digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:24]
        return cls(f"ge_{kind.value[:4]}_{digest}")

    def __str__(self) -> str:
        return self.value
