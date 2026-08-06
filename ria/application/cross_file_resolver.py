"""Cross-file Resolver application service.

Resolves symbol references across multiple files within a commit snapshot.
"""

from __future__ import annotations

from typing import Dict, List, Mapping, Sequence, Tuple

from ria.domain.models.symbol import Symbol
from ria.domain.models.symbol_reference import SymbolReference

__all__ = ["CrossFileResolverService"]


class CrossFileResolverService:
    """Service for resolving cross-file symbol references across commit file units."""

    def resolve_cross_file(
        self,
        file_references: Mapping[str, Sequence[SymbolReference]],
        all_symbols: Sequence[Symbol],
    ) -> Dict[str, Tuple[SymbolReference, ...]]:
        """Resolve unresolved references in file_references using all_symbols across the repository.

        Args:
            file_references: Path -> Sequence[SymbolReference] mapping for each file.
            all_symbols: Combined repository symbol table across all files in the commit.

        Returns:
            Path -> Tuple[SymbolReference, ...] mapping with cross-file references resolved.
        """
        # Build symbol lookup tables
        symbols_by_name: Dict[str, List[Symbol]] = {}
        symbols_by_qual: Dict[str, Symbol] = {}

        for sym in all_symbols:
            symbols_by_name.setdefault(sym.name, []).append(sym)
            symbols_by_qual[sym.qualified_name] = sym

        resolved_file_refs: Dict[str, Tuple[SymbolReference, ...]] = {}

        for path, refs in file_references.items():
            updated_refs: List[SymbolReference] = []

            for ref in refs:
                if ref.target.is_resolved:
                    updated_refs.append(ref)
                    continue

                target_name = ref.target.target_name

                # Try qualified name lookup first
                target_sym = symbols_by_qual.get(target_name)

                # Fallback to name lookup
                if target_sym is None:
                    candidates = symbols_by_name.get(target_name, [])
                    if len(candidates) == 1:
                        target_sym = candidates[0]

                if target_sym is not None:
                    resolved_target = ref.target.with_resolved(target_sym.symbol_id)
                    updated_ref = SymbolReference(
                        span=ref.span,
                        scope_id=ref.scope_id,
                        target=resolved_target,
                        kind=ref.kind,
                        location_file_path=ref.location_file_path,
                        source_symbol_id=ref.source_symbol_id,
                    )
                    updated_refs.append(updated_ref)
                else:
                    updated_refs.append(ref)

            resolved_file_refs[path] = tuple(updated_refs)

        return resolved_file_refs
