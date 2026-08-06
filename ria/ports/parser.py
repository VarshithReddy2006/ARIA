"""Parser layer ports — interfaces only, no implementations.

In accordance with SDD Section 7 (Hexagonal Architecture), every parser component
lives behind a :class:`typing.Protocol`. Nothing outside parser adapters ever imports
third-party parser libraries (e.g. tree-sitter) directly.

Ports defined at Milestone 3
----------------------------
``ParserPort``
    Engine interface that converts raw bytes into a language-agnostic ``SyntaxTree``.
``SyntaxExtractorPort``
    Extractor interface that turns a ``SyntaxTree`` into structured ``ExtractedSyntax``.
``LanguagePluginPort``
    Combined language plugin interface binding a grammar, queries, and extractors.
``ParserRegistryPort``
    Lookup and management interface for registered language plugins and parsers.
``ParseCacheStore``
    Persistence/caching port for caching ``ParseResult`` objects.
``CapabilityRegistryPort``
    Query interface for checking language and syntactic extraction capabilities.
"""

from __future__ import annotations

from typing import FrozenSet, Optional, Protocol, Sequence, Tuple, runtime_checkable

from ria.domain.enums import DeclarationKind, LanguageTier, ParserCapability
from ria.domain.models.file_unit import FileUnit
from ria.domain.models.language_plugin import LanguagePluginDescriptor
from ria.domain.models.parse_cache_entry import ParseCacheEntry
from ria.domain.models.parse_result import ParseResult
from ria.domain.models.parser_identity import (
    ComponentVersion,
    ParseCacheKey,
    ParserFingerprint,
)
from ria.domain.models.syntax_facts import ExtractedSyntax
from ria.domain.models.syntax_tree import SyntaxTree

__all__ = [
    "ParserPort",
    "SyntaxExtractorPort",
    "LanguagePluginPort",
    "ParserRegistryPort",
    "ParseCacheStore",
    "CapabilityRegistryPort",
]


@runtime_checkable
class ParserPort(Protocol):
    """Port for parsing raw source code bytes into a language-agnostic SyntaxTree.

    Tree-sitter exists only behind implementations of this interface.
    """

    def parse_bytes(
        self,
        source_bytes: bytes,
        *,
        language: str,
        content_hash: str,
        timeout_seconds: Optional[float] = None,
    ) -> SyntaxTree:
        """Parse source bytes into a SyntaxTree.

        Args:
            source_bytes: Raw source file bytes.
            language: Canonical language name (e.g., ``"python"``).
            content_hash: Canonical content hash of the source bytes.
            timeout_seconds: Optional parse execution timeout.

        Returns:
            The parsed SyntaxTree.

        Raises:
            ValueError: If language is unsupported or content_hash disagrees.
            InfrastructureError: If tree-sitter parsing fails catastrophic errors.
        """
        ...

    def parser_version(self, language: str) -> ComponentVersion:
        """Return the component version of the parser/grammar binding for a language."""
        ...


@runtime_checkable
class SyntaxExtractorPort(Protocol):
    """Port for extracting structured syntactic facts from a SyntaxTree."""

    def extract(self, tree: SyntaxTree, source_bytes: bytes) -> ExtractedSyntax:
        """Extract declarations, imports, exports, and comments from a tree.

        Args:
            tree: Syntax tree of the file.
            source_bytes: Raw source bytes (used for slicing identifier text).

        Returns:
            ExtractedSyntax containing all discovered syntactic facts.
        """
        ...

    def extractor_version(self) -> ComponentVersion:
        """Return the component version of this extractor."""
        ...

    def capabilities(self) -> FrozenSet[ParserCapability]:
        """Return the capabilities provided by this extractor."""
        ...


@runtime_checkable
class LanguagePluginPort(Protocol):
    """Port for a language plugin binding grammar, metadata, and extractors."""

    @property
    def descriptor(self) -> LanguagePluginDescriptor:
        """Static descriptor and capability declaration of the plugin."""
        ...

    def parse(
        self,
        unit: FileUnit,
        source_bytes: bytes,
        *,
        timeout_seconds: Optional[float] = None,
    ) -> ParseResult:
        """Parse a FileUnit and extract syntactic facts into a ParseResult.

        Args:
            unit: File unit describing path, content hash, and language.
            source_bytes: Raw file content bytes.
            timeout_seconds: Optional parse timeout.

        Returns:
            ParseResult containing the syntax tree, extracted syntax, timing,
            diagnostics, statistics, and fingerprint.
        """
        ...

    def fingerprint(self) -> ParserFingerprint:
        """Return the ParserFingerprint for results produced by this plugin."""
        ...


@runtime_checkable
class ParserRegistryPort(Protocol):
    """Port for managing and looking up language plugins and parsers."""

    def register_plugin(self, plugin: LanguagePluginPort) -> None:
        """Register a language plugin.

        Raises:
            ValueError: If a plugin for the language is already registered.
        """
        ...

    def get_plugin(self, language: str) -> Optional[LanguagePluginPort]:
        """Look up a language plugin by canonical language name."""
        ...

    def get_plugin_for_extension(self, extension: str) -> Optional[LanguagePluginPort]:
        """Look up a language plugin by file extension (e.g. ``".py"``)."""
        ...

    def list_plugins(self) -> Sequence[LanguagePluginPort]:
        """List all registered language plugins in deterministic order."""
        ...

    def list_supported_languages(self) -> Sequence[str]:
        """List all canonical language names supported by registered plugins."""
        ...

    def fingerprint_for(self, language: str) -> Optional[ParserFingerprint]:
        """Return the current ParserFingerprint for a language."""
        ...


@runtime_checkable
class ParseCacheStore(Protocol):
    """Port for persistence and retrieval of cached parse results."""

    def get(self, key: ParseCacheKey) -> Optional[ParseCacheEntry]:
        """Retrieve a cached parse result by cache key.

        Returns:
            The cached entry, or ``None`` if absent.
        """
        ...

    def put(self, entry: ParseCacheEntry) -> None:
        """Store a parse result entry in the cache.

        Args:
            entry: Parse cache entry to store.
        """
        ...

    def invalidate_by_reuse_key(self, reuse_key: str) -> int:
        """Invalidate all cached entries matching a reuse_key (content_hash|language).

        Returns:
            Number of invalidated cache entries.
        """
        ...

    def invalidate_by_fingerprint(self, fingerprint: ParserFingerprint) -> int:
        """Invalidate all cached entries produced under a specific fingerprint.

        Returns:
            Number of invalidated cache entries.
        """
        ...

    def clear(self) -> None:
        """Purge all entries from the parse cache."""
        ...


@runtime_checkable
class CapabilityRegistryPort(Protocol):
    """Port for querying parser and extractor capabilities across languages."""

    def capabilities_for_language(self, language: str) -> FrozenSet[ParserCapability]:
        """Get all capabilities declared for a canonical language."""
        ...

    def languages_with_capability(
        self, capability: ParserCapability
    ) -> Tuple[str, ...]:
        """List all languages that declare support for a specific capability."""
        ...

    def languages_with_declaration_kind(self, kind: DeclarationKind) -> Tuple[str, ...]:
        """List all languages that can extract a specific declaration kind."""
        ...

    def max_tier_for_language(self, language: str) -> LanguageTier:
        """Get the highest extraction tier available for a language."""
        ...
