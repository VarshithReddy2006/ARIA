"""Symbol Extractor application service.

Converts parser declarations into deterministic Symbol domain entities.
Implements :class:`~ria.ports.semantic.SymbolResolverPort`.
"""

from __future__ import annotations

from typing import Optional, Sequence, Tuple

from ria.domain.models.namespace_id import NamespaceId
from ria.domain.models.parser_identity import ParserFingerprint
from ria.domain.models.scope import Scope
from ria.domain.models.scope_id import ScopeId
from ria.domain.models.symbol import Symbol
from ria.domain.models.symbol_id import SymbolId
from ria.domain.models.syntax_facts import ExtractedSyntax
from ria.domain.models.syntax_tree import SyntaxTree
from ria.ports.semantic import SymbolResolverPort

__all__ = ["SymbolExtractorService"]


class SymbolExtractorService(SymbolResolverPort):
    """Service for extracting Symbol domain entities from parser declarations."""

    def extract_symbols(
        self,
        tree: SyntaxTree,
        extracted: ExtractedSyntax,
        scopes: Sequence[Scope],
        fingerprint: ParserFingerprint,
    ) -> Tuple[Symbol, ...]:
        """Extract Symbol entities from declarations and attach scope/namespace IDs.

        Args:
            tree: Parsed SyntaxTree.
            extracted: Syntactic declarations and comments.
            scopes: Sequence of Lexical Scope entities built for the file.
            fingerprint: Parser Fingerprint producing the source AST.

        Returns:
            Tuple of extracted Symbol entities.
        """
        symbols: list[Symbol] = []
        file_path = scopes[0].name if scopes and scopes[0].name else "file"

        # Build lookup table for scope IDs by span
        root_scope_id = (
            scopes[0].scope_id if scopes else ScopeId.root(tree.language, file_path)
        )

        for decl in extracted.declarations:
            # 1. Qualified name construction
            if decl.container_path:
                qual_name = ".".join((*decl.container_path, decl.name))
            else:
                qual_name = decl.name

            # 2. Determine enclosing scope
            enclosing_scope_id = root_scope_id
            smallest_size = float("inf")
            for scope in scopes:
                if scope.span.contains(decl.span):
                    size = scope.span.end.byte - scope.span.start.byte
                    if size < smallest_size:
                        smallest_size = size
                        enclosing_scope_id = scope.scope_id

            # 3. Determine namespace ID
            ns_id: Optional[NamespaceId] = None
            if decl.container_path:
                ns_path = ".".join(decl.container_path)
                ns_id = NamespaceId.for_namespace(tree.language, file_path, ns_path)

            # 4. Generate deterministic SymbolId
            sym_id = SymbolId.for_symbol(
                language=tree.language,
                file_path=file_path,
                qualified_name=qual_name,
                span=decl.span,
            )

            # 5. Create Symbol
            symbol = Symbol(
                symbol_id=sym_id,
                name=decl.name,
                qualified_name=qual_name,
                kind=decl.kind,
                language=tree.language,
                location=decl.span,
                visibility=decl.visibility,
                scope_id=enclosing_scope_id,
                namespace_id=ns_id,
                signature_text=decl.signature_text,
                documentation=decl.documentation,
                annotations=decl.annotations,
                parser_fingerprint=fingerprint,
            )
            symbols.append(symbol)

        return tuple(symbols)

    def resolve_symbol_by_id(
        self,
        symbol_id: SymbolId,
        symbols: Sequence[Symbol],
    ) -> Optional[Symbol]:
        """Look up a symbol by SymbolId within a symbol table sequence.

        Args:
            symbol_id: Identity of the target symbol.
            symbols: Known symbol sequence.

        Returns:
            The matching Symbol or None if unmapped.
        """
        for sym in symbols:
            if sym.symbol_id == symbol_id:
                return sym
        return None
