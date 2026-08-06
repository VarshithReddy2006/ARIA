"""Plugin Registry implementing ParserRegistryPort."""

from collections.abc import Sequence
from typing import Dict, Optional, Set

from ria.domain.index.value_objects import Language
from ria.plugins.core.exceptions import InvalidPluginError
from ria.plugins.core.interface import AbstractParser
from ria.plugins.core.metadata import PluginHealth, PluginHealthStatus
from ria.ports.index.parser_registry import ParserPluginPort, ParserRegistryPort


class PluginRegistry(ParserRegistryPort):
    """Central registry managing parser plugins, language mappings, health checks, and activation state."""

    def __init__(self) -> None:
        self._plugins_by_name: Dict[str, ParserPluginPort] = {}
        self._language_map: Dict[Language, ParserPluginPort] = {}
        self._disabled_names: Set[str] = set()

    def register_parser(self, language: Language, parser: ParserPluginPort) -> None:
        """Register a parser plugin instance for a language."""
        if not parser.can_parse(language):
            raise InvalidPluginError(
                f"Plugin '{parser.metadata.name}' declared inability to parse language '{language.value}'."
            )

        plugin_name = parser.metadata.name
        if (
            plugin_name in self._plugins_by_name
            and self._plugins_by_name[plugin_name] is not parser
        ):
            raise InvalidPluginError(
                f"Duplicate plugin registration attempted for plugin '{plugin_name}'."
            )

        self._plugins_by_name[plugin_name] = parser
        self._language_map[language] = parser

    def remove_parser(self, language: Language) -> bool:
        """Unregister parser plugin for language. Returns True if removed."""
        if language in self._language_map:
            parser = self._language_map.pop(language)
            # If no other language uses this parser, remove from _plugins_by_name
            if parser not in self._language_map.values():
                self._plugins_by_name.pop(parser.metadata.name, None)
            return True
        return False

    def get_parser(self, language: Language) -> Optional[ParserPluginPort]:
        """Lookup active, non-disabled parser plugin registered for language."""
        parser = self._language_map.get(language)
        if parser is None:
            return None
        if parser.metadata.name in self._disabled_names:
            return None
        return parser

    def enable_plugin(self, plugin_name: str) -> bool:
        """Enable a plugin by name. Returns True if plugin exists and enabled."""
        if plugin_name in self._plugins_by_name:
            self._disabled_names.discard(plugin_name)
            return True
        return False

    def disable_plugin(self, plugin_name: str) -> bool:
        """Disable a plugin by name. Returns True if plugin exists and disabled."""
        if plugin_name in self._plugins_by_name:
            self._disabled_names.add(plugin_name)
            return True
        return False

    def supported_languages(self) -> Sequence[Language]:
        """Return sequence of languages with registered, active parser plugins."""
        return tuple(
            lang
            for lang, parser in self._language_map.items()
            if parser.metadata.name not in self._disabled_names
        )

    def check_all_health(self) -> Sequence[PluginHealth]:
        """Perform health checks across all registered plugins."""
        results: list[PluginHealth] = []
        for plugin_name, parser in self._plugins_by_name.items():
            if plugin_name in self._disabled_names:
                results.append(
                    PluginHealth(
                        plugin_id=plugin_name,
                        status=PluginHealthStatus.DISABLED,
                        message="Plugin manually disabled.",
                    )
                )
            elif isinstance(parser, AbstractParser):
                results.append(parser.check_health())
            else:
                results.append(
                    PluginHealth(
                        plugin_id=plugin_name,
                        status=PluginHealthStatus.HEALTHY,
                        message="Port compliant plugin.",
                    )
                )
        return tuple(results)
