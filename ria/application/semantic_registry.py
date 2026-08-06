"""Semantic Registry application service.

Manages language-specific semantic resolution plugins and capabilities.
Implements :class:`~ria.ports.semantic.SemanticRegistryPort`.
"""

from __future__ import annotations

from typing import Dict, FrozenSet, Optional

from ria.domain.models.parser_identity import ComponentVersion
from ria.ports.semantic import SemanticRegistryPort, SemanticResolutionPort

__all__ = ["SemanticRegistry"]


class SemanticRegistry(SemanticRegistryPort):
    """Thread-safe registry for language-specific semantic resolvers."""

    def __init__(self) -> None:
        self._resolvers: Dict[str, SemanticResolutionPort] = {}

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
        key = language.strip().lower()
        if not key:
            raise ValueError("language must be non-empty")
        if key in self._resolvers:
            raise ValueError(
                f"semantic resolver for language {language!r} already registered"
            )
        self._resolvers[key] = resolver

    def get_resolver(self, language: str) -> Optional[SemanticResolutionPort]:
        """Look up a semantic resolver by language name."""
        key = language.strip().lower()
        return self._resolvers.get(key)

    def supported_languages(self) -> FrozenSet[str]:
        """Return the set of languages with registered semantic resolvers."""
        return frozenset(self._resolvers.keys())

    def resolver_version(self, language: str) -> Optional[ComponentVersion]:
        """Return ComponentVersion for a language's resolver."""
        resolver = self.get_resolver(language)
        return resolver.resolver_version() if resolver is not None else None
