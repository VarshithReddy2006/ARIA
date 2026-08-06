"""Language Resolver Registry Port Protocol."""

from collections.abc import Sequence
from typing import Optional, Protocol, runtime_checkable

from ria.domain.index.value_objects import Language
from ria.ports.resolution.language_resolver import LanguageResolverPort


@runtime_checkable
class LanguageResolverRegistryPort(Protocol):
    """Protocol for discovering, registering, and retrieving LanguageResolverPort instances."""

    def register_resolver(self, language: Language, resolver: LanguageResolverPort) -> None:
        """Register a language resolver instance for a specific language."""
        ...

    def get_resolver(self, language: Language) -> Optional[LanguageResolverPort]:
        """Lookup active LanguageResolverPort registered for language."""
        ...

    def supported_languages(self) -> Sequence[Language]:
        """Return sequence of languages with registered language resolvers."""
        ...
