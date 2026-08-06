"""Unit tests for Phase 2 semantic resolution ports.

Verifies runtime checkability, protocol shapes, and absence of external infrastructure leaks.
"""

from __future__ import annotations

from typing import FrozenSet, Optional, Sequence, Tuple

from ria.domain.enums import SemanticCapability
from ria.domain.models.file_unit import FileUnit
from ria.domain.models.inheritance import InheritanceRelation, OverrideRelation
from ria.domain.models.namespace import Namespace
from ria.domain.models.parse_result import ParseResult
from ria.domain.models.parser_identity import ComponentVersion, ParserFingerprint
from ria.domain.models.scope import Scope
from ria.domain.models.semantic_identity import SemanticCacheKey, SemanticFingerprint
from ria.domain.models.semantic_result import ResolutionResult
from ria.domain.models.symbol import Symbol
from ria.domain.models.symbol_id import SymbolId
from ria.domain.models.symbol_reference import SymbolReference
from ria.domain.models.syntax_facts import ExtractedSyntax
from ria.domain.models.syntax_tree import SyntaxTree
from ria.ports.semantic import (
    ImportResolverPort,
    InheritanceResolverPort,
    NamespaceResolverPort,
    ReferenceResolverPort,
    ScopeResolverPort,
    SemanticCacheStore,
    SemanticRegistryPort,
    SemanticResolutionPort,
    SymbolResolverPort,
)


class DummyScopeResolver:
    def build_scopes(
        self, tree: SyntaxTree, extracted: ExtractedSyntax
    ) -> Tuple[Scope, ...]:
        return ()

    def build_root_scope(self, unit: FileUnit) -> Scope:
        raise NotImplementedError


class DummySymbolResolver:
    def extract_symbols(
        self,
        tree: SyntaxTree,
        extracted: ExtractedSyntax,
        scopes: Sequence[Scope],
        fingerprint: ParserFingerprint,
    ) -> Tuple[Symbol, ...]:
        return ()

    def resolve_symbol_by_id(
        self, symbol_id: SymbolId, symbols: Sequence[Symbol]
    ) -> Optional[Symbol]:
        return None


class DummyNamespaceResolver:
    def build_namespaces(
        self, unit: FileUnit, extracted: ExtractedSyntax
    ) -> Tuple[Namespace, ...]:
        return ()


class DummyImportResolver:
    def resolve_imports(
        self,
        unit: FileUnit,
        extracted: ExtractedSyntax,
        available_symbols: Sequence[Symbol],
    ) -> Tuple[SymbolReference, ...]:
        return ()


class DummyReferenceResolver:
    def resolve_references(
        self,
        tree: SyntaxTree,
        extracted: ExtractedSyntax,
        scopes: Sequence[Scope],
        symbols: Sequence[Symbol],
    ) -> Tuple[SymbolReference, ...]:
        return ()


class DummyInheritanceResolver:
    def resolve_inheritance(
        self,
        extracted: ExtractedSyntax,
        symbols: Sequence[Symbol],
    ) -> Tuple[Tuple[InheritanceRelation, ...], Tuple[OverrideRelation, ...]]:
        return ((), ())


class DummySemanticCacheStore:
    def get(self, key: SemanticCacheKey) -> Optional[ResolutionResult]:
        return None

    def put(self, key: SemanticCacheKey, result: ResolutionResult) -> None:
        pass

    def invalidate_by_reuse_key(self, reuse_key: str) -> int:
        return 0

    def invalidate_by_fingerprint(self, fingerprint: SemanticFingerprint) -> int:
        return 0

    def clear(self) -> None:
        pass


class DummySemanticRegistry:
    def register_resolver(
        self, language: str, resolver: SemanticResolutionPort
    ) -> None:
        pass

    def get_resolver(self, language: str) -> Optional[SemanticResolutionPort]:
        return None

    def supported_languages(self) -> FrozenSet[str]:
        return frozenset()

    def resolver_version(self, language: str) -> Optional[ComponentVersion]:
        return None


class DummySemanticResolutionService:
    def resolve_unit(
        self,
        unit: FileUnit,
        parse_result: ParseResult,
        context_symbols: Sequence[Symbol] = (),
    ) -> ResolutionResult:
        return ResolutionResult()

    def resolver_version(self) -> ComponentVersion:
        return ComponentVersion("dummy", "1.0.0")

    def capabilities(self) -> FrozenSet[SemanticCapability]:
        return frozenset(
            {SemanticCapability.RESOLVE_SCOPES, SemanticCapability.RESOLVE_SYMBOLS}
        )


def test_scope_resolver_port_conformance() -> None:
    dummy = DummyScopeResolver()
    assert isinstance(dummy, ScopeResolverPort)


def test_symbol_resolver_port_conformance() -> None:
    dummy = DummySymbolResolver()
    assert isinstance(dummy, SymbolResolverPort)


def test_namespace_resolver_port_conformance() -> None:
    dummy = DummyNamespaceResolver()
    assert isinstance(dummy, NamespaceResolverPort)


def test_import_resolver_port_conformance() -> None:
    dummy = DummyImportResolver()
    assert isinstance(dummy, ImportResolverPort)


def test_reference_resolver_port_conformance() -> None:
    dummy = DummyReferenceResolver()
    assert isinstance(dummy, ReferenceResolverPort)


def test_inheritance_resolver_port_conformance() -> None:
    dummy = DummyInheritanceResolver()
    assert isinstance(dummy, InheritanceResolverPort)


def test_semantic_cache_store_conformance() -> None:
    dummy = DummySemanticCacheStore()
    assert isinstance(dummy, SemanticCacheStore)


def test_semantic_registry_port_conformance() -> None:
    dummy = DummySemanticRegistry()
    assert isinstance(dummy, SemanticRegistryPort)


def test_semantic_resolution_port_conformance() -> None:
    dummy = DummySemanticResolutionService()
    assert isinstance(dummy, SemanticResolutionPort)
