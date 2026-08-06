"""Plugin Loader for discovering and registering parser plugins."""

from typing import Type

from ria.plugins.core.exceptions import PluginLoadError
from ria.plugins.core.interface import AbstractParser
from ria.plugins.core.registry import PluginRegistry


class PluginLoader:
    """Loader responsible for instantiating and registering parser plugins into PluginRegistry."""

    def __init__(self, registry: PluginRegistry) -> None:
        self._registry = registry

    def load_plugin_instance(self, plugin: AbstractParser) -> None:
        """Register a pre-instantiated parser plugin across all its supported languages."""
        try:
            for lang in plugin.capabilities.supported_languages:
                self._registry.register_parser(lang, plugin)
        except Exception as err:
            raise PluginLoadError(f"Failed to load plugin '{plugin.metadata.name}': {err}") from err

    def load_plugin_class(self, plugin_cls: Type[AbstractParser]) -> AbstractParser:
        """Instantiate and register a parser plugin class."""
        try:
            instance = plugin_cls()
            self.load_plugin_instance(instance)
            return instance
        except Exception as err:
            raise PluginLoadError(f"Failed to instantiate plugin class '{plugin_cls.__name__}': {err}") from err
