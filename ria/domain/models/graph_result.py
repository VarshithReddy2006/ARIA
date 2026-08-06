"""Graph result and observability value objects.

Defines GraphStatistics, GraphMetadata, GraphDiagnostic, and TraversalResult.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping, Optional, Tuple

from ria.domain.enums import DiagnosticSeverity, EdgeKind, NodeKind
from ria.domain.models.graph_edge import GraphEdge
from ria.domain.models.graph_node import GraphNode
from ria.domain.models.graph_node_id import GraphNodeId

__all__ = [
    "GraphStatistics",
    "GraphMetadata",
    "GraphDiagnostic",
    "TraversalResult",
]


@dataclass(frozen=True)
class GraphStatistics:
    """Quantitative metrics of a constructed Repository Knowledge Graph.

    Attributes:
        nodes_total: Count of total nodes.
        edges_total: Count of total edges.
        nodes_by_kind: Mapping of NodeKind to node count.
        edges_by_kind: Mapping of EdgeKind to edge count.
    """

    nodes_total: int = 0
    edges_total: int = 0
    nodes_by_kind: Mapping[NodeKind, int] = field(default_factory=dict)
    edges_by_kind: Mapping[EdgeKind, int] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphMetadata:
    """Provenance metadata for a constructed graph.

    Attributes:
        repository_id: Identity of the repository.
        commit_sha: Identity of the commit snapshot.
        created_at_iso: UTC timestamp when the graph was built.
        builder_version: Version of the builder.
        schema_version: Version of the graph schema.
    """

    repository_id: str
    commit_sha: str
    created_at_iso: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    builder_version: str = "1.0.0"
    schema_version: str = "1.0.0"


@dataclass(frozen=True)
class GraphDiagnostic:
    """Diagnostic message emitted during graph construction or traversal.

    Attributes:
        severity: DiagnosticSeverity level.
        message: Diagnostic text explanation.
        code: Diagnostic error/warning code string.
        node_id: Optional node associated with the diagnostic.
    """

    severity: DiagnosticSeverity
    message: str
    code: str = "GRAPH_DIAGNOSTIC"
    node_id: Optional[GraphNodeId] = None


@dataclass(frozen=True)
class TraversalResult:
    """Result of a deterministic graph traversal operation.

    Attributes:
        visited_nodes: Sequence of visited GraphNode instances in traversal order.
        traversed_edges: Sequence of traversed GraphEdge instances in traversal order.
        path_length: Length of the traversal path in edges.
        reachability_score: Reachability metric (0.0 to 1.0).
    """

    visited_nodes: Tuple[GraphNode, ...] = ()
    traversed_edges: Tuple[GraphEdge, ...] = ()
    path_length: int = 0
    reachability_score: float = 1.0
