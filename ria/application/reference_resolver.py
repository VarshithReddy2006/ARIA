"""Reference Resolver application service.

Resolves identifier occurrences to target symbols following lexical scoping rules.
Implements :class:`~ria.ports.semantic.ReferenceResolverPort`.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from ria.domain.enums import ReferenceKind
from ria.domain.models.scope import Scope
from ria.domain.models.scope_id import ScopeId
from ria.domain.models.span import SourceSpan
from ria.domain.models.symbol import Symbol
from ria.domain.models.symbol_id import SymbolId
from ria.domain.models.symbol_reference import ReferenceTarget, SymbolReference
from ria.domain.models.syntax_facts import ExtractedSyntax
from ria.domain.models.syntax_tree import SyntaxNode, SyntaxTree
from ria.ports.semantic import ReferenceResolverPort

__all__ = ["ReferenceResolverService"]


class ReferenceResolverService(ReferenceResolverPort):
    """Service for resolving identifier occurrences to target symbols."""

    def resolve_references(
        self,
        tree: SyntaxTree,
        extracted: ExtractedSyntax,
        scopes: Sequence[Scope],
        symbols: Sequence[Symbol],
    ) -> Tuple[SymbolReference, ...]:
        """Resolve identifier occurrences against accessible symbols following lexical scoping rules.

        Args:
            tree: Parsed SyntaxTree.
            extracted: Extracted syntax facts.
            scopes: Lexical Scope hierarchy.
            symbols: Available Symbols in local and module scope.

        Returns:
            Tuple of resolved and unresolved SymbolReference instances.
        """
        references: List[SymbolReference] = []
        file_path = scopes[0].name if scopes and scopes[0].name else "file"

        # Build Scope parent map and scope symbol map
        scope_by_id: Dict[ScopeId, Scope] = {s.scope_id: s for s in scopes}
        symbols_by_scope: Dict[ScopeId, List[Symbol]] = {}
        for sym in symbols:
            symbols_by_scope.setdefault(sym.scope_id, []).append(sym)

        # Collect identifier nodes from AST
        identifier_nodes: List[Tuple[SyntaxNode, ReferenceKind]] = []
        self._collect_identifier_nodes(tree.root, identifier_nodes)

        for node, kind in identifier_nodes:
            # 1. Determine enclosing scope
            enclosing_scope = self._find_enclosing_scope(node.span, scopes)
            scope_id = (
                enclosing_scope.scope_id if enclosing_scope else scopes[0].scope_id
            )

            # Node text / identifier name
            id_name = node.field_name or node.kind

            # 2. Scope traversal (inner to outer, implementing shadowing)
            resolved_sym: Optional[Symbol] = None
            curr_scope_id: Optional[ScopeId] = scope_id

            while curr_scope_id is not None:
                scope_syms = symbols_by_scope.get(curr_scope_id, [])
                for s in scope_syms:
                    if s.name == id_name:
                        resolved_sym = s
                        break
                if resolved_sym is not None:
                    break

                curr_scope = scope_by_id.get(curr_scope_id)
                curr_scope_id = curr_scope.parent_id if curr_scope else None

            # Fallback global search if not found in parent scopes
            if resolved_sym is None:
                for s in symbols:
                    if s.name == id_name:
                        resolved_sym = s
                        break

            target_id: Optional[SymbolId] = (
                resolved_sym.symbol_id if resolved_sym else None
            )
            target = ReferenceTarget(
                target_name=id_name,
                target_symbol_id=target_id,
                is_resolved=target_id is not None,
            )

            ref = SymbolReference(
                span=node.span,
                scope_id=scope_id,
                target=target,
                kind=kind,
                location_file_path=file_path,
            )
            references.append(ref)

        return tuple(references)

    def _collect_identifier_nodes(
        self,
        node: SyntaxNode,
        out: List[Tuple[SyntaxNode, ReferenceKind]],
    ) -> None:
        """Traverse AST and collect identifier references."""
        if node.kind in ("identifier", "type_identifier", "property_identifier"):
            kind = ReferenceKind.READ
            if node.field_name == "call" or (
                node.children and any(c.kind == "argument_list" for c in node.children)
            ):
                kind = ReferenceKind.CALL
            out.append((node, kind))

        for child in node.children:
            self._collect_identifier_nodes(child, out)

    def _find_enclosing_scope(
        self,
        span: SourceSpan,
        scopes: Sequence[Scope],
    ) -> Optional[Scope]:
        """Find smallest enclosing scope for span."""
        enclosing = [s for s in scopes if s.span.contains(span)]
        if not enclosing:
            return None
        return min(enclosing, key=lambda s: s.span.end.byte - s.span.start.byte)
