"""Language Resolver Registry implementing LanguageResolverRegistryPort."""

from collections.abc import Sequence
from typing import Dict, Optional

from ria.domain.index.value_objects import Language
from ria.ports.resolution.language_resolver import LanguageResolverPort
from ria.ports.resolution.registry import LanguageResolverRegistryPort


class LanguageResolverRegistry(LanguageResolverRegistryPort):
    """Central registry mapping Language enum values to LanguageResolverPort instances."""

    def __init__(self) -> None:
        self._resolvers: Dict[Language, LanguageResolverPort] = {}

    def register_resolver(
        self, language: Language, resolver: LanguageResolverPort
    ) -> None:
        """Register a language resolver instance for a specific language."""
        if not resolver.can_resolve(language):
            raise ValueError(
                f"Resolver declared inability to resolve language '{language.value}'."
            )
        self._resolvers[language] = resolver

    def get_resolver(self, language: Language) -> Optional[LanguageResolverPort]:
        """Lookup active LanguageResolverPort registered for language."""
        return self._resolvers.get(language)

    def supported_languages(self) -> Sequence[Language]:
        """Return sequence of languages with registered language resolvers."""
        return tuple(self._resolvers.keys())
