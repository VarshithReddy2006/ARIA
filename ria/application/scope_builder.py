"""Scope Builder application service.

Constructs deterministic lexical scope hierarchies from parsed SyntaxTree and ExtractedSyntax.
Implements :class:`~ria.ports.semantic.ScopeResolverPort`.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from ria.domain.enums import ScopeKind
from ria.domain.models.file_unit import FileUnit
from ria.domain.models.scope import Scope
from ria.domain.models.scope_id import ScopeId
from ria.domain.models.span import SourcePosition, SourceSpan
from ria.domain.models.syntax_facts import ExtractedSyntax
from ria.domain.models.syntax_tree import SyntaxNode, SyntaxTree
from ria.ports.semantic import ScopeResolverPort

__all__ = ["ScopeBuilder"]

# Mapping AST node kinds or syntax forms to ScopeKind
_AST_NODE_SCOPE_KINDS = {
    "class_definition": ScopeKind.CLASS,
    "function_definition": ScopeKind.FUNCTION,
    "interface_declaration": ScopeKind.INTERFACE,
    "enum_declaration": ScopeKind.ENUM,
    "struct_declaration": ScopeKind.STRUCT,
    "namespace_declaration": ScopeKind.NAMESPACE,
    "module": ScopeKind.MODULE,
    "program": ScopeKind.MODULE,
    "block": ScopeKind.BLOCK,
    "statement_block": ScopeKind.BLOCK,
    "list_comprehension": ScopeKind.COMPREHENSION,
    "dictionary_comprehension": ScopeKind.COMPREHENSION,
    "set_comprehension": ScopeKind.COMPREHENSION,
    "generator_expression": ScopeKind.COMPREHENSION,
    "lambda": ScopeKind.LAMBDA,
    "arrow_function": ScopeKind.LAMBDA,
}


class ScopeBuilder(ScopeResolverPort):
    """Deterministic lexical scope hierarchy builder."""

    def build_root_scope(self, unit: FileUnit) -> Scope:
        """Construct the root module scope for a file unit.

        Args:
            unit: FileUnit under analysis.

        Returns:
            Root module Scope.
        """
        root_id = ScopeId.root(unit.language, unit.path)
        dummy_pos = SourcePosition(byte=0, line=0, column=0)
        dummy_span = SourceSpan(start=dummy_pos, end=dummy_pos)
        return Scope(
            scope_id=root_id,
            kind=ScopeKind.MODULE,
            span=dummy_span,
            language=unit.language,
            name=unit.path,
            parent_id=None,
        )

    def build_scopes(
        self,
        tree: SyntaxTree,
        extracted: ExtractedSyntax,
        file_path: str = "file",
    ) -> Tuple[Scope, ...]:
        """Construct the complete lexical scope hierarchy for a parsed file.

        Args:
            tree: Parsed language-agnostic SyntaxTree.
            extracted: Extracted syntax facts.
            file_path: Normalised repository-relative file path.

        Returns:
            Tuple of Scope entities ordered hierarchically (root scope first).
        """
        scopes: List[Scope] = []

        # 1. Root Module Scope
        root_id = ScopeId.root(tree.language, file_path)
        root_scope = Scope(
            scope_id=root_id,
            kind=ScopeKind.MODULE,
            span=tree.root.span,
            language=tree.language,
            name=file_path,
            parent_id=None,
        )
        scopes.append(root_scope)

        # 2. Traverse AST nodes recursively to collect scope nodes
        scope_nodes: List[Tuple[SyntaxNode, ScopeKind, Optional[str]]] = []
        self._find_scope_nodes(tree.root, tree.language, scope_nodes)

        # Sort scope nodes by span size descending (outer scopes first)
        scope_nodes.sort(
            key=lambda item: item[0].span.end.byte - item[0].span.start.byte,
            reverse=True,
        )

        # Build Scope objects with deterministic parent pointer resolution
        created_scopes: List[Scope] = [root_scope]

        for node, kind, name in scope_nodes:
            # Skip root node if matched
            if node == tree.root:
                continue

            # Determine parent scope by finding the smallest enclosing scope in created_scopes
            parent = self._find_enclosing_scope(node.span, created_scopes)
            parent_id = parent.scope_id if parent is not None else root_id

            # In Python/JS methods inside class scopes
            if (
                kind is ScopeKind.FUNCTION
                and parent is not None
                and parent.kind in (ScopeKind.CLASS, ScopeKind.INTERFACE)
            ):
                kind = ScopeKind.METHOD

            scope_id = ScopeId.for_scope(
                tree.language, file_path, kind, name, node.span
            )
            new_scope = Scope(
                scope_id=scope_id,
                kind=kind,
                span=node.span,
                language=tree.language,
                name=name,
                parent_id=parent_id,
            )
            created_scopes.append(new_scope)

        # 3. Sort scopes deterministically by span start byte, then span end byte
        result = sorted(
            created_scopes, key=lambda s: (s.span.start.byte, -s.span.end.byte)
        )
        return tuple(result)

    def _find_scope_nodes(
        self,
        node: SyntaxNode,
        language: str,
        out: List[Tuple[SyntaxNode, ScopeKind, Optional[str]]],
    ) -> None:
        """Collect nodes that introduce lexical scopes."""
        kind = _AST_NODE_SCOPE_KINDS.get(node.kind)
        if kind is not None:
            # Determine scope name if available
            name = None
            if kind in (
                ScopeKind.CLASS,
                ScopeKind.FUNCTION,
                ScopeKind.INTERFACE,
                ScopeKind.STRUCT,
                ScopeKind.ENUM,
                ScopeKind.NAMESPACE,
            ):
                for child in node.children:
                    if child.kind in (
                        "identifier",
                        "type_identifier",
                        "property_identifier",
                        "name",
                    ):
                        name = child.field_name or child.kind
                        break

            out.append((node, kind, name))

        for child in node.children:
            self._find_scope_nodes(child, language, out)

    def _find_enclosing_scope(
        self,
        span: SourceSpan,
        scopes: Sequence[Scope],
    ) -> Optional[Scope]:
        """Find the smallest enclosing scope for a given span."""
        enclosing: List[Scope] = []
        for scope in scopes:
            if scope.span.contains(span):
                enclosing.append(scope)

        if not enclosing:
            return None

        # Return the scope with the smallest span size
        return min(enclosing, key=lambda s: s.span.end.byte - s.span.start.byte)
