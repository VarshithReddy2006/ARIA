"""Exceptions for RIA Plugin Engine."""


class PluginError(Exception):
    """Base exception for all plugin engine failures."""

    pass


class PluginLoadError(PluginError):
    """Raised when a plugin fails to load or initialize."""

    pass


class ParserError(PluginError):
    """Raised when a parser plugin encounters an unrecoverable syntax/parsing error."""

    pass


class UnsupportedLanguageError(PluginError):
    """Raised when requesting a parser for an unsupported or unregistered language."""

    pass


class InvalidPluginError(PluginError):
    """Raised when a plugin manifest or implementation violates contract rules."""

    pass
