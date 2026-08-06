"""Edge Builder application service.

Generates deterministic directed GraphEdge entities from semantic resolution results.
Implements :class:`~ria.ports.graph.EdgeBuilderPort`.
"""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

from ria.domain.enums import EdgeKind, InheritanceKind, ReferenceKind
from ria.domain.models.graph_edge import GraphEdge
from ria.domain.models.graph_edge_id import GraphEdgeId
from ria.domain.models.graph_node import GraphNode
from ria.domain.models.scope_id import ScopeId
from ria.domain.models.semantic_result import ResolutionResult
from ria.domain.models.symbol_id import SymbolId
from ria.ports.graph import EdgeBuilderPort

__all__ = ["EdgeBuilderService"]


class EdgeBuilderService(EdgeBuilderPort):
    """Service for constructing deterministic GraphEdge entities."""

    def build_edges(
        self,
        nodes: Sequence[GraphNode],
        resolution_result: ResolutionResult,
    ) -> Tuple[GraphEdge, ...]:
        """Generate directed GraphEdge instances connecting nodes based on semantic facts.

        Args:
            nodes: Sequence of all constructed GraphNode entities.
            resolution_result: Composite semantic resolution result.

        Returns:
            Tuple of deterministic GraphEdge entities.
        """
        edges: List[GraphEdge] = []

        # Index nodes by symbol_id and scope_id
        node_by_symbol: Dict[SymbolId, GraphNode] = {
            n.symbol_id: n for n in nodes if n.symbol_id is not None
        }
        node_by_scope: Dict[ScopeId, GraphNode] = {
            n.scope_id: n for n in nodes if n.scope_id is not None
        }

        # 1. Structural CONTAINS / DEFINED_IN edges from Symbols & Scopes
        for n in nodes:
            if n.symbol_id is not None and n.scope_id is not None:
                scope_node = node_by_scope.get(n.scope_id)
                if scope_node is not None:
                    # scope_node CONTAINS n
                    eid1 = GraphEdgeId.for_edge(
                        EdgeKind.CONTAINS, scope_node.node_id, n.node_id
                    )
                    edges.append(
                        GraphEdge(
                            edge_id=eid1,
                            kind=EdgeKind.CONTAINS,
                            source_id=scope_node.node_id,
                            target_id=n.node_id,
                        )
                    )

                    # n DEFINED_IN scope_node
                    eid2 = GraphEdgeId.for_edge(
                        EdgeKind.DEFINED_IN, n.node_id, scope_node.node_id
                    )
                    edges.append(
                        GraphEdge(
                            edge_id=eid2,
                            kind=EdgeKind.DEFINED_IN,
                            source_id=n.node_id,
                            target_id=scope_node.node_id,
                        )
                    )

        # 2. Reference edges (CALLS, IMPORTS, EXPORTS, REFERENCES, USES)
        for ref in resolution_result.references:
            if not ref.target.is_resolved or ref.target.target_symbol_id is None:
                continue

            target_node = node_by_symbol.get(ref.target.target_symbol_id)
            source_scope_node = node_by_scope.get(ref.scope_id)

            if target_node is not None and source_scope_node is not None:
                edge_kind = _REFERENCE_KIND_TO_EDGE_KIND.get(
                    ref.kind, EdgeKind.REFERENCES
                )
                eid = GraphEdgeId.for_edge(
                    edge_kind, source_scope_node.node_id, target_node.node_id
                )
                edges.append(
                    GraphEdge(
                        edge_id=eid,
                        kind=edge_kind,
                        source_id=source_scope_node.node_id,
                        target_id=target_node.node_id,
                    )
                )

        # 3. Inheritance edges (EXTENDS, IMPLEMENTS)
        for inh in resolution_result.inheritance_relations:
            if inh.parent_symbol_id is not None:
                child_node = node_by_symbol.get(inh.child_symbol_id)
                parent_node = node_by_symbol.get(inh.parent_symbol_id)

                if child_node is not None and parent_node is not None:
                    edge_kind = (
                        EdgeKind.EXTENDS
                        if inh.kind is InheritanceKind.EXTENDS
                        else EdgeKind.IMPLEMENTS
                    )
                    eid = GraphEdgeId.for_edge(
                        edge_kind, child_node.node_id, parent_node.node_id
                    )
                    edges.append(
                        GraphEdge(
                            edge_id=eid,
                            kind=edge_kind,
                            source_id=child_node.node_id,
                            target_id=parent_node.node_id,
                        )
                    )

        # 4. Override edges (OVERRIDES)
        for ovr in resolution_result.override_relations:
            overriding_node = node_by_symbol.get(ovr.overriding_symbol_id)
            overridden_node = node_by_symbol.get(ovr.overridden_symbol_id)

            if overriding_node is not None and overridden_node is not None:
                eid = GraphEdgeId.for_edge(
                    EdgeKind.OVERRIDES, overriding_node.node_id, overridden_node.node_id
                )
                edges.append(
                    GraphEdge(
                        edge_id=eid,
                        kind=EdgeKind.OVERRIDES,
                        source_id=overriding_node.node_id,
                        target_id=overridden_node.node_id,
                    )
                )

        # Deduplicate edges by edge_id
        unique_edges: Dict[GraphEdgeId, GraphEdge] = {e.edge_id: e for e in edges}
        return tuple(unique_edges.values())


_REFERENCE_KIND_TO_EDGE_KIND = {
    ReferenceKind.CALL: EdgeKind.CALLS,
    ReferenceKind.IMPORT: EdgeKind.IMPORTS,
    ReferenceKind.EXPORT: EdgeKind.EXPORTS,
    ReferenceKind.READ: EdgeKind.REFERENCES,
    ReferenceKind.WRITE: EdgeKind.USES,
    ReferenceKind.TYPE_USE: EdgeKind.USES,
}
