"""Parser Registry Port abstraction and Parser Plugin contract."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

from ria.domain.index.units import ParserResult
from ria.domain.index.value_objects import FilePath, Language


@dataclass(frozen=True, slots=True)
class PluginMetadata:
    """Immutable metadata describing a parser plugin."""

    name: str
    version: str
    author: str
    description: str


@dataclass(frozen=True, slots=True)
class PluginCapabilities:
    """Immutable capability manifest for a parser plugin."""

    supported_languages: Sequence[Language]
    supports_async: bool = False
    max_file_size_bytes: int = 2 * 1024 * 1024


@runtime_checkable
class ParserPluginPort(Protocol):
    """Protocol representing an executable Tree-sitter parser plugin for a specific language.

    Preconditions: Code bytes must be valid bytes. FilePath must be relative.
    Postconditions: Returns immutable ParserResult containing AST root node and parse metrics.
    """

    @property
    def metadata(self) -> PluginMetadata:
        """Return plugin metadata descriptor."""
        ...

    @property
    def capabilities(self) -> PluginCapabilities:
        """Return plugin capability manifest."""
        ...

    def can_parse(self, language: Language) -> bool:
        """Return True if plugin can parse code written in language."""
        ...

    def parse(self, path: FilePath, code: bytes) -> ParserResult:
        """Parse source code bytes into immutable AST ParserResult."""
        ...


@runtime_checkable
class ParserRegistryPort(Protocol):
    """Protocol for discovering, registering, and retrieving ParserPluginPort instances.

    Preconditions: Language must be a valid Language enum value.
    Postconditions: Resolves active parser plugin for language.
    """

    def register_parser(self, language: Language, parser: ParserPluginPort) -> None:
        """Register a parser plugin instance for a language."""
        ...

    def remove_parser(self, language: Language) -> bool:
        """Unregister parser plugin for language. Returns True if removed."""
        ...

    def get_parser(self, language: Language) -> Optional[ParserPluginPort]:
        """Lookup active parser plugin registered for language."""
        ...

    def supported_languages(self) -> Sequence[Language]:
        """Return sequence of languages with registered parser plugins."""
        ...
