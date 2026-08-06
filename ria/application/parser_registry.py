"""Parser registry for language plugins.

Implements :class:`~ria.ports.parser.ParserRegistryPort` to manage language plugins,
extension mapping, capabilities, and component version fingerprints.
"""

from __future__ import annotations

import threading
from typing import Dict, Optional, Sequence

from ria.domain.models.parser_identity import ParserFingerprint
from ria.ports.parser import LanguagePluginPort, ParserRegistryPort

__all__ = ["ParserRegistry"]


class ParserRegistry(ParserRegistryPort):
    """Thread-safe registry for language plugins.

    Features:
    - Language plugin lookup by canonical language name or file extension.
    - Component version fingerprint tracking per language.
    - Prevents ambiguous extension claims or duplicate language registrations.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_language: Dict[str, LanguagePluginPort] = {}
        self._by_extension: Dict[str, LanguagePluginPort] = {}

    def register_plugin(self, plugin: LanguagePluginPort) -> None:
        """Register a language plugin.

        Args:
            plugin: Language plugin instance implementing LanguagePluginPort.

        Raises:
            ValueError: If a plugin for the language or any extension is already registered.
        """
        descriptor = plugin.descriptor
        language = descriptor.language

        with self._lock:
            if language in self._by_language:
                raise ValueError(
                    f"language plugin for {language!r} is already registered"
                )

            for ext in descriptor.extensions:
                if ext in self._by_extension:
                    existing_lang = self._by_extension[ext].descriptor.language
                    raise ValueError(
                        f"extension {ext!r} is already claimed by language plugin {existing_lang!r}"
                    )

            self._by_language[language] = plugin
            for ext in descriptor.extensions:
                self._by_extension[ext] = plugin

    def get_plugin(self, language: str) -> Optional[LanguagePluginPort]:
        """Look up a language plugin by canonical language name."""
        with self._lock:
            return self._by_language.get(language.lower())

    def get_plugin_for_extension(self, extension: str) -> Optional[LanguagePluginPort]:
        """Look up a language plugin by file extension (e.g., ``".py"``)."""
        with self._lock:
            return self._by_extension.get(extension.lower())

    def list_plugins(self) -> Sequence[LanguagePluginPort]:
        """List all registered language plugins in deterministic language name order."""
        with self._lock:
            return tuple(
                self._by_language[lang] for lang in sorted(self._by_language.keys())
            )

    def list_supported_languages(self) -> Sequence[str]:
        """List all supported canonical language names in alphabetical order."""
        with self._lock:
            return tuple(sorted(self._by_language.keys()))

    def fingerprint_for(self, language: str) -> Optional[ParserFingerprint]:
        """Return the current ParserFingerprint for a language."""
        plugin = self.get_plugin(language)
        return plugin.fingerprint() if plugin is not None else None
