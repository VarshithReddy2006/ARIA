"""Semantic resolution ports — interfaces only, no implementations.

In accordance with SDD Section 7 (Hexagonal Architecture), every semantic resolution
component lives behind a :class:`typing.Protocol`.
"""

from __future__ import annotations

from typing import FrozenSet, Optional, Protocol, Sequence, Tuple, runtime_checkable

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

__all__ = [
    "ScopeResolverPort",
    "SymbolResolverPort",
    "NamespaceResolverPort",
    "ImportResolverPort",
    "ReferenceResolverPort",
    "InheritanceResolverPort",
    "SemanticCacheStore",
    "SemanticRegistryPort",
    "SemanticResolutionPort",
]


@runtime_checkable
class ScopeResolverPort(Protocol):
    """Port for constructing lexical scopes from syntax trees and facts."""

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

        Returns:
            Tuple of Scope entities ordered hierarchically (root scope first).
        """
        ...

    def build_root_scope(self, unit: FileUnit) -> Scope:
        """Construct the root module scope for a file unit.

        Args:
            unit: FileUnit under resolution.

        Returns:
            Root module Scope.
        """
        ...


@runtime_checkable
class SymbolResolverPort(Protocol):
    """Port for converting syntactic declarations into semantic Symbol entities."""

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
        ...

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
        ...


@runtime_checkable
class NamespaceResolverPort(Protocol):
    """Port for resolving logical package and module namespace hierarchies."""

    def build_namespaces(
        self,
        unit: FileUnit,
        extracted: ExtractedSyntax,
    ) -> Tuple[Namespace, ...]:
        """Construct namespace containers for a file unit.

        Args:
            unit: FileUnit being processed.
            extracted: Extracted syntax facts.

        Returns:
            Tuple of Namespace entities.
        """
        ...


@runtime_checkable
class ImportResolverPort(Protocol):
    """Port for resolving import/export statements into symbol references."""

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
        ...


@runtime_checkable
class ReferenceResolverPort(Protocol):
    """Port for resolving identifier occurrences to target symbols in scope."""

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
        ...


@runtime_checkable
class InheritanceResolverPort(Protocol):
    """Port for resolving subtyping, trait implementation, and method override relations."""

    def resolve_inheritance(
        self,
        extracted: ExtractedSyntax,
        symbols: Sequence[Symbol],
    ) -> Tuple[Tuple[InheritanceRelation, ...], Tuple[OverrideRelation, ...]]:
        """Resolve inheritance clauses and method overrides among class/interface symbols.

        Args:
            extracted: Extracted syntax facts.
            symbols: Known candidate type and method symbols.

        Returns:
            Tuple of:
            - Tuple of InheritanceRelation instances
            - Tuple of OverrideRelation instances
        """
        ...


@runtime_checkable
class SemanticCacheStore(Protocol):
    """Port for durable caching of semantic ResolutionResults."""

    def get(self, key: SemanticCacheKey) -> Optional[ResolutionResult]:
        """Retrieve a cached ResolutionResult by SemanticCacheKey.

        Args:
            key: Cache key.

        Returns:
            Cached ResolutionResult or None if absent.
        """
        ...

    def put(self, key: SemanticCacheKey, result: ResolutionResult) -> None:
        """Store a ResolutionResult in the semantic cache.

        Args:
            key: Cache key.
            result: ResolutionResult to cache.
        """
        ...

    def invalidate_by_reuse_key(self, reuse_key: str) -> int:
        """Purge cached entries matching a content/language reuse key.

        Args:
            reuse_key: String of the form "{content_hash}|{language}".

        Returns:
            Count of purged records.
        """
        ...

    def invalidate_by_fingerprint(self, fingerprint: SemanticFingerprint) -> int:
        """Purge cached entries produced under a specific resolver/parser fingerprint.

        Args:
            fingerprint: SemanticFingerprint to purge.

        Returns:
            Count of purged records.
        """
        ...

    def clear(self) -> None:
        """Purge all entries from the semantic cache."""
        ...


@runtime_checkable
class SemanticRegistryPort(Protocol):
    """Port for managing language-specific semantic resolvers and capabilities."""

    def register_resolver(
        self,
        language: str,
        resolver: SemanticResolutionPort,
    ) -> None:
        """Register a semantic resolver for a language.

        Args:
            language: Canonical language name.
            resolver: SemanticResolutionPort implementation.
        """
        ...

    def get_resolver(self, language: str) -> Optional[SemanticResolutionPort]:
        """Look up a semantic resolver by language name.

        Args:
            language: Canonical language name.

        Returns:
            SemanticResolutionPort or None if unregistered.
        """
        ...

    def supported_languages(self) -> FrozenSet[str]:
        """Return the set of languages with registered semantic resolvers."""
        ...

    def resolver_version(self, language: str) -> Optional[ComponentVersion]:
        """Return ComponentVersion for a language's resolver."""
        ...


@runtime_checkable
class SemanticResolutionPort(Protocol):
    """Port for performing semantic resolution over a single FileUnit and ParseResult."""

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
        ...

    def resolver_version(self) -> ComponentVersion:
        """Return identity and version of this resolver implementation."""
        ...

    def capabilities(self) -> FrozenSet[SemanticCapability]:
        """Return declared semantic capabilities for this language resolver."""
        ...
