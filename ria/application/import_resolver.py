"""Import and Export Resolver application service.

Resolves imports, exports, aliases, namespace imports, and re-exports into SymbolReferences.
Implements :class:`~ria.ports.semantic.ImportResolverPort`.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

from ria.domain.enums import ReferenceKind
from ria.domain.models.file_unit import FileUnit
from ria.domain.models.scope_id import ScopeId
from ria.domain.models.symbol import Symbol
from ria.domain.models.symbol_reference import ReferenceTarget, SymbolReference
from ria.domain.models.syntax_facts import ExtractedSyntax
from ria.ports.semantic import ImportResolverPort

__all__ = ["ImportResolverService"]


class ImportResolverService(ImportResolverPort):
    """Service for resolving imports, exports, and re-exports."""

    def resolve_imports(
        self,
        unit: FileUnit,
        extracted: ExtractedSyntax,
        available_symbols: Sequence[Symbol],
    ) -> Tuple[SymbolReference, ...]:
        """Resolve import and export statements into explicit SymbolReferences.

        Args:
            unit: FileUnit containing the import/export statements.
            extracted: Extracted syntax facts containing imports and exports.
            available_symbols: Sequence of candidate target symbols across files.

        Returns:
            Tuple of SymbolReference objects representing imports/exports.
        """
        references: List[SymbolReference] = []
        root_scope_id = ScopeId.root(unit.language, unit.path)

        # Build symbol table mapping for candidate symbols: name -> Symbol
        symbol_map = {sym.name: sym for sym in available_symbols}
        qual_symbol_map = {sym.qualified_name: sym for sym in available_symbols}

        # 1. Process Imports
        for imp in extracted.imports:
            for imported_name in imp.names:
                target_name = imported_name.name

                # Try matching target name in symbol maps
                target_symbol = symbol_map.get(target_name) or qual_symbol_map.get(
                    target_name
                )
                target_id = (
                    target_symbol.symbol_id if target_symbol is not None else None
                )

                target = ReferenceTarget(
                    target_name=target_name,
                    target_symbol_id=target_id,
                    is_resolved=target_id is not None,
                    module_moniker=imp.module_text,
                )

                ref = SymbolReference(
                    span=imp.span,
                    scope_id=root_scope_id,
                    target=target,
                    kind=ReferenceKind.IMPORT,
                    location_file_path=unit.path,
                )
                references.append(ref)

        # 2. Process Exports
        for exp in extracted.exports:
            for exported_name in exp.names:
                target_name = exported_name.name
                target_symbol = symbol_map.get(target_name) or qual_symbol_map.get(
                    target_name
                )
                target_id = (
                    target_symbol.symbol_id if target_symbol is not None else None
                )

                target = ReferenceTarget(
                    target_name=target_name,
                    target_symbol_id=target_id,
                    is_resolved=target_id is not None,
                    module_moniker=exp.module_text,
                )

                ref = SymbolReference(
                    span=exp.span,
                    scope_id=root_scope_id,
                    target=target,
                    kind=ReferenceKind.EXPORT,
                    location_file_path=unit.path,
                )
                references.append(ref)

        return tuple(references)
