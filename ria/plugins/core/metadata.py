"""Metadata, capabilities, and health status for RIA plugins."""

from dataclasses import dataclass
from enum import Enum

from ria.plugins.core.exceptions import InvalidPluginError
from ria.ports.index.parser_registry import PluginCapabilities, PluginMetadata


class PluginHealthStatus(Enum):
    """Health check status for a registered plugin."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    DISABLED = "DISABLED"


@dataclass(frozen=True, slots=True)
class PluginVersion:
    """Semantic versioning for plugins."""

    major: int
    minor: int
    patch: int

    def _validate_invariants(self) -> None:
        if self.major < 0 or self.minor < 0 or self.patch < 0:
            raise InvalidPluginError("PluginVersion numbers cannot be negative.")

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True, slots=True)
class PluginHealth:
    """Health status check result for a plugin."""

    plugin_id: str
    status: PluginHealthStatus
    message: str = "Plugin operating normally."


__all__ = [
    "PluginHealthStatus",
    "PluginVersion",
    "PluginCapabilities",
    "PluginMetadata",
    "PluginHealth",
]
