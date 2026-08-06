"""Capability registry for querying parser capabilities across languages.

Implements :class:`~ria.ports.parser.CapabilityRegistryPort` using a
:class:`~ria.ports.parser.ParserRegistryPort`.
"""

from __future__ import annotations

from typing import FrozenSet, Tuple

from ria.domain.enums import DeclarationKind, LanguageTier, ParserCapability
from ria.ports.parser import CapabilityRegistryPort, ParserRegistryPort

__all__ = ["CapabilityRegistry"]


class CapabilityRegistry(CapabilityRegistryPort):
    """Registry for querying syntax and extraction capabilities across languages.

    Attributes:
        parser_registry: Parser registry containing active language plugins.
    """

    def __init__(self, parser_registry: ParserRegistryPort) -> None:
        self._registry = parser_registry

    def capabilities_for_language(self, language: str) -> FrozenSet[ParserCapability]:
        """Get all capabilities declared for a canonical language."""
        plugin = self._registry.get_plugin(language)
        if plugin is None:
            return frozenset()
        return plugin.descriptor.capabilities

    def languages_with_capability(
        self, capability: ParserCapability
    ) -> Tuple[str, ...]:
        """List all languages that declare support for a specific capability."""
        supported = []
        for plugin in self._registry.list_plugins():
            if plugin.descriptor.supports(capability):
                supported.append(plugin.descriptor.language)
        return tuple(sorted(supported))

    def languages_with_declaration_kind(self, kind: DeclarationKind) -> Tuple[str, ...]:
        """List all languages that can extract a specific declaration kind."""
        supported = []
        for plugin in self._registry.list_plugins():
            for cap in plugin.descriptor.capabilities:
                if cap.declaration_kind == kind:
                    supported.append(plugin.descriptor.language)
                    break
        return tuple(sorted(supported))

    def max_tier_for_language(self, language: str) -> LanguageTier:
        """Get the highest extraction tier available for a language."""
        plugin = self._registry.get_plugin(language)
        if plugin is None:
            return LanguageTier.NONE
        return plugin.descriptor.tier
