"""Unit tests for EdgeBuilderService (Phase 4)."""

from __future__ import annotations


from ria.application.graph_edge_builder import EdgeBuilderService
from ria.domain.enums import DeclarationKind, EdgeKind, ReferenceKind
from ria.domain.models.graph_node import GraphNode
from ria.domain.models.graph_node_id import GraphNodeId
from ria.domain.models.scope_id import ScopeId
from ria.domain.models.semantic_result import ResolutionResult
from ria.domain.models.span import SourcePosition, SourceSpan
from ria.domain.models.symbol_id import SymbolId
from ria.domain.models.symbol_reference import ReferenceTarget, SymbolReference


def test_build_edges() -> None:
    pos = SourcePosition(0, 0, 0)
    span = SourceSpan(pos, pos)

    sym1_id = SymbolId.for_symbol("python", "app.py", "caller", span)
    sym2_id = SymbolId.for_symbol("python", "app.py", "callee", span)
    scope_id = ScopeId.root("python", "app.py")

    node1 = GraphNode(
        node_id=GraphNodeId("n1"),
        kind=DeclarationKind.FUNCTION,
        name="caller",
        symbol_id=sym1_id,
        scope_id=scope_id,
    )
    node2 = GraphNode(
        node_id=GraphNodeId("n2"),
        kind=DeclarationKind.FUNCTION,
        name="callee",
        symbol_id=sym2_id,
        scope_id=scope_id,
    )
    scope_node = GraphNode(
        node_id=GraphNodeId("ns"),
        kind=DeclarationKind.FUNCTION,
        name="root",
        scope_id=scope_id,
    )

    target = ReferenceTarget(
        target_name="callee", target_symbol_id=sym2_id, is_resolved=True
    )
    ref = SymbolReference(
        span=span,
        scope_id=scope_id,
        target=target,
        kind=ReferenceKind.CALL,
        location_file_path="app.py",
    )
    res = ResolutionResult(references=(ref,))

    builder = EdgeBuilderService()
    edges = builder.build_edges((node1, node2, scope_node), res)

    assert len(edges) >= 1
    call_edges = [e for e in edges if e.kind is EdgeKind.CALLS]
    assert len(call_edges) == 1
    assert call_edges[0].source_id == scope_node.node_id
    assert call_edges[0].target_id == node2.node_id
