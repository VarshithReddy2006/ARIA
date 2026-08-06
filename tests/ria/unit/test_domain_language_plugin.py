"""Tests for PluginIdentity, ExtractorDescriptor, and LanguagePluginDescriptor."""

from __future__ import annotations

import pytest

from ria.domain.enums import LanguageTier, ParserCapability
from ria.domain.models.language_plugin import (
    ExtractorDescriptor,
    LanguagePluginDescriptor,
    PluginIdentity,
)
from ria.domain.models.parser_identity import ComponentVersion, ParserFingerprint


def make_version(name: str = "comp", ver: str = "1.0.0") -> ComponentVersion:
    return ComponentVersion(name=name, version=ver)


class TestPluginIdentity:
    def test_valid_identity(self) -> None:
        identity = PluginIdentity(language="python", version=make_version("py-plugin"))
        assert identity.language == "python"
        assert str(identity) == "python@1.0.0"

    def test_empty_language_raises(self) -> None:
        with pytest.raises(ValueError, match="language must be non-empty"):
            PluginIdentity(language="", version=make_version())

    def test_uppercase_language_raises(self) -> None:
        with pytest.raises(ValueError, match="language must be lowercase"):
            PluginIdentity(language="Python", version=make_version())


class TestExtractorDescriptor:
    def test_valid_extractor(self) -> None:
        extractor = ExtractorDescriptor(
            name="py-extractor",
            version=make_version("py-extractor"),
            capabilities=frozenset({ParserCapability.EXTRACT_FUNCTIONS}),
        )
        assert extractor.name == "py-extractor"
        assert extractor.supports(ParserCapability.EXTRACT_FUNCTIONS)
        assert not extractor.supports(ParserCapability.EXTRACT_CLASSES)

    def test_empty_name_raises(self) -> None:
        with pytest.raises(ValueError, match="extractor name must be non-empty"):
            ExtractorDescriptor(name="", version=make_version())


class TestLanguagePluginDescriptor:
    def test_valid_descriptor(self) -> None:
        identity = PluginIdentity(
            language="python", version=make_version("py-plugin", "1.0.0")
        )
        extractor = ExtractorDescriptor(
            name="py-extractor",
            version=make_version("py-extractor", "1.2.0"),
            capabilities=frozenset({ParserCapability.EXTRACT_FUNCTIONS}),
        )
        parser_ver = make_version("tree-sitter-python", "0.21.0")

        plugin = LanguagePluginDescriptor(
            identity=identity,
            extensions=(".py", ".pyi"),
            grammar_name="python",
            parser_version=parser_ver,
            extractor=extractor,
            tier=LanguageTier.TIER_A,
            capabilities=frozenset(
                {ParserCapability.PARSE, ParserCapability.PRODUCE_AST}
            ),
        )

        assert plugin.language == "python"
        assert plugin.extensions == (".py", ".pyi")
        assert plugin.supports(ParserCapability.PARSE)
        assert plugin.supports(ParserCapability.PRODUCE_AST)
        assert plugin.supports(ParserCapability.EXTRACT_FUNCTIONS)

        expected_fingerprint = ParserFingerprint(
            parser=parser_ver,
            extractor=extractor.version,
            language=identity.version,
        )
        assert plugin.fingerprint == expected_fingerprint

    def test_missing_minimum_capabilities_raises(self) -> None:
        identity = PluginIdentity(language="python", version=make_version("py-plugin"))
        extractor = ExtractorDescriptor(name="py-ext", version=make_version("py-ext"))

        with pytest.raises(ValueError, match="must declare minimum capabilities"):
            LanguagePluginDescriptor(
                identity=identity,
                extensions=(".py",),
                grammar_name="python",
                parser_version=make_version("parser"),
                extractor=extractor,
                capabilities=frozenset({ParserCapability.PARSE}),  # missing PRODUCE_AST
            )

    def test_invalid_extension_raises(self) -> None:
        identity = PluginIdentity(language="python", version=make_version("py-plugin"))
        extractor = ExtractorDescriptor(name="py-ext", version=make_version("py-ext"))

        with pytest.raises(
            ValueError, match="extension must be lowercase and start with a dot"
        ):
            LanguagePluginDescriptor(
                identity=identity,
                extensions=("py",),  # missing dot
                grammar_name="python",
                parser_version=make_version("parser"),
                extractor=extractor,
                capabilities=frozenset(
                    {ParserCapability.PARSE, ParserCapability.PRODUCE_AST}
                ),
            )
