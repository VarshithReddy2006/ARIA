"""Tests for parser layer ports runtime checkability and signatures."""

from __future__ import annotations

from typing import FrozenSet, Optional, Sequence, Tuple

from ria.domain.enums import DeclarationKind, LanguageTier, ParserCapability
from ria.domain.models.file_unit import FileUnit
from ria.domain.models.language_plugin import (
    ExtractorDescriptor,
    LanguagePluginDescriptor,
    PluginIdentity,
)
from ria.domain.models.parse_cache_entry import ParseCacheEntry
from ria.domain.models.parse_result import ParseResult
from ria.domain.models.parser_identity import (
    ComponentVersion,
    ParseCacheKey,
    ParserFingerprint,
)
from ria.domain.models.syntax_facts import ExtractedSyntax
from ria.domain.models.syntax_tree import SyntaxTree
from ria.ports.parser import (
    CapabilityRegistryPort,
    LanguagePluginPort,
    ParseCacheStore,
    ParserPort,
    ParserRegistryPort,
    SyntaxExtractorPort,
)


class DummyParserAdapter:
    def parse_bytes(
        self,
        source_bytes: bytes,
        *,
        language: str,
        content_hash: str,
        timeout_seconds: Optional[float] = None,
    ) -> SyntaxTree:
        raise NotImplementedError

    def parser_version(self, language: str) -> ComponentVersion:
        return ComponentVersion("tree-sitter", "0.21.0")


class DummySyntaxExtractor:
    def extract(self, tree: SyntaxTree, source_bytes: bytes) -> ExtractedSyntax:
        return ExtractedSyntax()

    def extractor_version(self) -> ComponentVersion:
        return ComponentVersion("dummy-extractor", "1.0.0")

    def capabilities(self) -> FrozenSet[ParserCapability]:
        return frozenset({ParserCapability.EXTRACT_FUNCTIONS})


class DummyLanguagePlugin:
    @property
    def descriptor(self) -> LanguagePluginDescriptor:
        return LanguagePluginDescriptor(
            identity=PluginIdentity("python", ComponentVersion("plugin", "1.0.0")),
            extensions=(".py",),
            grammar_name="python",
            parser_version=ComponentVersion("tree-sitter-python", "0.21.0"),
            extractor=ExtractorDescriptor(
                "py-ext", ComponentVersion("py-ext", "1.0.0")
            ),
            capabilities=frozenset(
                {ParserCapability.PARSE, ParserCapability.PRODUCE_AST}
            ),
        )

    def parse(
        self,
        unit: FileUnit,
        source_bytes: bytes,
        *,
        timeout_seconds: Optional[float] = None,
    ) -> ParseResult:
        raise NotImplementedError

    def fingerprint(self) -> ParserFingerprint:
        return self.descriptor.fingerprint


class DummyParserRegistry:
    def register_plugin(self, plugin: LanguagePluginPort) -> None:
        pass

    def get_plugin(self, language: str) -> Optional[LanguagePluginPort]:
        return None

    def get_plugin_for_extension(self, extension: str) -> Optional[LanguagePluginPort]:
        return None

    def list_plugins(self) -> Sequence[LanguagePluginPort]:
        return ()

    def list_supported_languages(self) -> Sequence[str]:
        return ()

    def fingerprint_for(self, language: str) -> Optional[ParserFingerprint]:
        return None


class DummyParseCacheStore:
    def get(self, key: ParseCacheKey) -> Optional[ParseCacheEntry]:
        return None

    def put(self, entry: ParseCacheEntry) -> None:
        pass

    def invalidate_by_reuse_key(self, reuse_key: str) -> int:
        return 0

    def invalidate_by_fingerprint(self, fingerprint: ParserFingerprint) -> int:
        return 0

    def clear(self) -> None:
        pass


class DummyCapabilityRegistry:
    def capabilities_for_language(self, language: str) -> FrozenSet[ParserCapability]:
        return frozenset()

    def languages_with_capability(
        self, capability: ParserCapability
    ) -> Tuple[str, ...]:
        return ()

    def languages_with_declaration_kind(self, kind: DeclarationKind) -> Tuple[str, ...]:
        return ()

    def max_tier_for_language(self, language: str) -> LanguageTier:
        return LanguageTier.NONE


def test_parser_ports_conformance() -> None:
    assert isinstance(DummyParserAdapter(), ParserPort)
    assert isinstance(DummySyntaxExtractor(), SyntaxExtractorPort)
    assert isinstance(DummyLanguagePlugin(), LanguagePluginPort)
    assert isinstance(DummyParserRegistry(), ParserRegistryPort)
    assert isinstance(DummyParseCacheStore(), ParseCacheStore)
    assert isinstance(DummyCapabilityRegistry(), CapabilityRegistryPort)
