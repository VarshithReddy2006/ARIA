"""Semantic Resolution Service application service.

Orchestrates semantic resolution across scopes, symbols, imports, references, and inheritance.
Implements :class:`~ria.ports.semantic.SemanticResolutionPort`.
"""

from __future__ import annotations

import time
from typing import FrozenSet, Optional, Sequence

from ria.application.import_resolver import ImportResolverService
from ria.application.inheritance_resolver import InheritanceResolverService
from ria.application.reference_resolver import ReferenceResolverService
from ria.application.scope_builder import ScopeBuilder
from ria.application.symbol_extractor import SymbolExtractorService
from ria.domain.enums import SemanticCapability
from ria.domain.models.file_unit import FileUnit
from ria.domain.models.parse_result import ParseResult
from ria.domain.models.parser_identity import ComponentVersion
from ria.domain.models.semantic_identity import SemanticCacheKey, SemanticFingerprint
from ria.domain.models.semantic_result import (
    ResolutionResult,
    ResolutionStatistics,
    ResolutionTiming,
)
from ria.domain.models.symbol import Symbol
from ria.ports.semantic import SemanticCacheStore, SemanticResolutionPort

__all__ = ["SemanticResolutionService"]


class SemanticResolutionService(SemanticResolutionPort):
    """High-level service orchestrating semantic resolution."""

    def __init__(
        self,
        cache_store: Optional[SemanticCacheStore] = None,
        resolver_version: str = "1.0.0",
    ) -> None:
        self._cache_store = cache_store
        self._version = resolver_version
        self._scope_builder = ScopeBuilder()
        self._symbol_extractor = SymbolExtractorService()
        self._import_resolver = ImportResolverService()
        self._reference_resolver = ReferenceResolverService()
        self._inheritance_resolver = InheritanceResolverService()

    def resolver_version(self) -> ComponentVersion:
        """Return identity and version of this resolver implementation."""
        return ComponentVersion(name="default-semantic-resolver", version=self._version)

    def capabilities(self) -> FrozenSet[SemanticCapability]:
        """Return declared semantic capabilities."""
        return frozenset(
            {
                SemanticCapability.RESOLVE_SCOPES,
                SemanticCapability.RESOLVE_SYMBOLS,
                SemanticCapability.RESOLVE_IMPORTS,
                SemanticCapability.RESOLVE_EXPORTS,
                SemanticCapability.RESOLVE_REFERENCES,
                SemanticCapability.RESOLVE_CROSS_FILE,
                SemanticCapability.RESOLVE_INHERITANCE,
            }
        )

    def resolve_unit(
        self,
        unit: FileUnit,
        parse_result: ParseResult,
        context_symbols: Sequence[Symbol] = (),
    ) -> ResolutionResult:
        """Resolve semantic scopes, symbols, references, and inheritance for a file unit.

        Args:
            unit: FileUnit under resolution.
            parse_result: Output from the parser layer.
            context_symbols: Optional cross-file symbol table for import/inheritance resolution.

        Returns:
            Complete ResolutionResult.
        """
        # Return empty result if parse failed or tree missing
        if parse_result.tree is None:
            return ResolutionResult()

        # Check Cache if store present
        sem_fp = SemanticFingerprint(
            resolver_name=self.resolver_version().name,
            resolver_version=self.resolver_version().version,
            parser_fingerprint=parse_result.fingerprint,
            language=unit.language,
        )
        cache_key = SemanticCacheKey(
            content_hash=unit.content_hash,
            language=unit.language,
            fingerprint=sem_fp,
        )

        if self._cache_store is not None:
            cached = self._cache_store.get(cache_key)
            if cached is not None:
                return cached

        t_start = time.perf_counter()

        # 1. Scopes
        t0 = time.perf_counter()
        scopes = self._scope_builder.build_scopes(
            parse_result.tree, parse_result.extracted, file_path=unit.path
        )
        t_scope = time.perf_counter() - t0

        # 2. Symbols
        t0 = time.perf_counter()
        symbols = self._symbol_extractor.extract_symbols(
            parse_result.tree, parse_result.extracted, scopes, parse_result.fingerprint
        )
        t_sym = time.perf_counter() - t0

        # 3. Imports
        t0 = time.perf_counter()
        combined_context = tuple(symbols) + tuple(context_symbols)
        import_refs = self._import_resolver.resolve_imports(
            unit, parse_result.extracted, combined_context
        )
        t_imp = time.perf_counter() - t0

        # 4. References
        t0 = time.perf_counter()
        code_refs = self._reference_resolver.resolve_references(
            parse_result.tree, parse_result.extracted, scopes, combined_context
        )
        t_ref = time.perf_counter() - t0

        # 5. Inheritance
        t0 = time.perf_counter()
        inh_rels, ovr_rels = self._inheritance_resolver.resolve_inheritance(
            parse_result.extracted, combined_context
        )
        t_inh = time.perf_counter() - t0

        t_total = time.perf_counter() - t_start

        all_refs = import_refs + code_refs
        resolved_count = sum(1 for r in all_refs if r.target.is_resolved)

        stats = ResolutionStatistics(
            symbols_total=len(symbols),
            scopes_total=len(scopes),
            references_total=len(all_refs),
            references_resolved=resolved_count,
            inheritance_relations_total=len(inh_rels),
            override_relations_total=len(ovr_rels),
            diagnostics_total=len(parse_result.diagnostics),
        )

        timing = ResolutionTiming(
            scope_seconds=t_scope,
            symbol_seconds=t_sym,
            import_seconds=t_imp,
            reference_seconds=t_ref,
            inheritance_seconds=t_inh,
            total_seconds=t_total,
        )

        result = ResolutionResult(
            symbols=symbols,
            scopes=scopes,
            references=all_refs,
            inheritance_relations=inh_rels,
            override_relations=ovr_rels,
            statistics=stats,
            timing=timing,
            from_cache=False,
        )

        # Store in cache if store present
        if self._cache_store is not None:
            self._cache_store.put(cache_key, result)

        return result
