"""Language Resolver Port Protocol."""

from typing import Any, Protocol, runtime_checkable

from ria.domain.index.units import ParseUnit
from ria.domain.index.value_objects import Language
from ria.domain.resolution.entities import ResolvedFactSet


@runtime_checkable
class LanguageResolverPort(Protocol):
    """Protocol representing a language-specific semantic symbol and relationship resolver.

    Preconditions: ParseUnit must contain a valid ASTUnit. Context must be a valid ResolutionContext.
    Postconditions: Returns immutable ResolvedFactSet containing extracted symbols and relations.
    """

    def can_resolve(self, language: Language) -> bool:
        """Return True if this resolver supports the given programming language."""
        ...

    def resolve_unit(self, parse_unit: ParseUnit, context: Any) -> ResolvedFactSet:
        """Extract symbols and resolve definitions, references, calls, and imports for a single ParseUnit."""
        ...
