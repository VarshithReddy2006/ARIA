"""Parser Plugin Interface and Abstract Parser Base Class."""

from abc import ABC, abstractmethod

from ria.domain.index.units import ParserResult
from ria.domain.index.value_objects import FilePath, Language
from ria.plugins.core.metadata import PluginHealth, PluginHealthStatus
from ria.ports.index.parser_registry import ParserPluginPort, PluginMetadata


class AbstractParser(ParserPluginPort, ABC):
    """Abstract Base Class for all Parser Plugins, extending ParserPluginPort contract."""

    @property
    @abstractmethod
    def metadata(self) -> PluginMetadata:
        """Return plugin metadata descriptor."""
        ...

    def can_parse(self, language: Language) -> bool:
        """Return True if plugin can parse code written in language."""
        return language in self.capabilities.supported_languages

    def check_health(self) -> PluginHealth:
        """Perform health check on parser plugin."""
        return PluginHealth(
            plugin_id=self.metadata.name,
            status=PluginHealthStatus.HEALTHY,
            message="Parser plugin ready.",
        )

    @abstractmethod
    def parse(self, path: FilePath, code: bytes) -> ParserResult:
        """Parse source code bytes into immutable AST ParserResult."""
        ...
