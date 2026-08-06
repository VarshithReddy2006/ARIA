"""Language plugin capability descriptor and identity models.

These value objects describe a language plugin's identity, capability declaration, and
extractor registration. They are domain value objects consumed by the parser registry,
the capability registry, and the language plugin system.

Design note
-----------
A :class:`LanguagePluginDescriptor` describes a plugin's static metadata and capability
declaration. It is *not* the plugin implementation itself: the execution protocol
(which loads grammars, parses bytes into ASTs, and extracts syntactic facts) belongs
to the ports layer, keeping third-party parsing libraries strictly outside the domain.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Tuple

from ria.domain.enums import LanguageTier, ParserCapability, MINIMUM_PARSER_CAPABILITIES
from ria.domain.models.parser_identity import ComponentVersion, ParserFingerprint

__all__ = ["PluginIdentity", "ExtractorDescriptor", "LanguagePluginDescriptor"]


@dataclass(frozen=True)
class PluginIdentity:
    """The identity and version of a language plugin.

    Attributes:
        language: Canonical language name, e.g., ``"python"``.
        version: Plugin version component.
    """

    language: str
    version: ComponentVersion

    def __post_init__(self) -> None:
        if not self.language:
            raise ValueError("language must be non-empty")
        if self.language != self.language.lower():
            raise ValueError(f"language must be lowercase, got {self.language!r}")

    def __str__(self) -> str:
        return f"{self.language}@{self.version.version}"


@dataclass(frozen=True)
class ExtractorDescriptor:
    """Description of an extractor set attached to a language plugin.

    Attributes:
        name: Extractor component name, e.g., ``"python-extractor"``.
        version: Extractor version component.
        capabilities: Syntactic capabilities this extractor provides.
    """

    name: str
    version: ComponentVersion
    capabilities: FrozenSet[ParserCapability] = frozenset()

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("extractor name must be non-empty")
        object.__setattr__(self, "capabilities", frozenset(self.capabilities))

    def supports(self, capability: ParserCapability) -> bool:
        """Whether the extractor provides a given capability."""
        return capability in self.capabilities

    def __str__(self) -> str:
        return f"{self.name}@{self.version.version} ({len(self.capabilities)} capabilities)"


@dataclass(frozen=True)
class LanguagePluginDescriptor:
    """Complete declaration and identity of a language plugin.

    Attributes:
        identity: Plugin identity containing language name and version.
        extensions: Supported file extensions including the leading dot, e.g. ``(".py", ".pyi")``.
        grammar_name: Tree-sitter grammar name or identifier, e.g. ``"python"``.
        parser_version: Parser component version for tree-sitter or parser engine.
        extractor: Extractor descriptor describing extracted syntax capabilities.
        tier: Declared extraction tier (e.g. ``LanguageTier.TIER_A``).
        capabilities: Aggregated parser capabilities. Must include at least ``PARSE``
            and ``PRODUCE_AST``.
    """

    identity: PluginIdentity
    extensions: Tuple[str, ...]
    grammar_name: str
    parser_version: ComponentVersion
    extractor: ExtractorDescriptor
    tier: LanguageTier = LanguageTier.TIER_A
    capabilities: FrozenSet[ParserCapability] = frozenset()

    def __post_init__(self) -> None:
        if not self.grammar_name:
            raise ValueError("grammar_name must be non-empty")
        for ext in self.extensions:
            if not ext.startswith(".") or ext != ext.lower():
                raise ValueError(
                    f"extension must be lowercase and start with a dot, got {ext!r}"
                )
        object.__setattr__(self, "extensions", tuple(self.extensions))

        # Merge plugin capabilities with extractor capabilities
        merged = set(self.capabilities) | set(self.extractor.capabilities)
        object.__setattr__(self, "capabilities", frozenset(merged))

        # Enforce minimum required capabilities
        missing = MINIMUM_PARSER_CAPABILITIES - self.capabilities
        if missing:
            raise ValueError(
                f"language plugin for {self.identity.language!r} must declare minimum "
                f"capabilities {sorted(missing)}"
            )

    @property
    def language(self) -> str:
        """Canonical language name."""
        return self.identity.language

    @property
    def fingerprint(self) -> ParserFingerprint:
        """Build the ParserFingerprint for results produced by this plugin."""
        return ParserFingerprint(
            parser=self.parser_version,
            extractor=self.extractor.version,
            language=self.identity.version,
        )

    def supports(self, capability: ParserCapability) -> bool:
        """Whether this plugin supports the specified syntactic capability."""
        return capability in self.capabilities

    def __str__(self) -> str:
        return f"LanguagePlugin({self.language}, tier={self.tier.value}, caps={len(self.capabilities)})"
