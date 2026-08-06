"""Twin Registry application service.

Tracks Twin Version, Schema Version, Builder Version, and supported capabilities.
Implements :class:`~ria.ports.twin.TwinRegistryPort`.
"""

from __future__ import annotations

from typing import FrozenSet

from ria.domain.models.parser_identity import ComponentVersion
from ria.domain.models.twin_identity import TwinVersion
from ria.ports.twin import TwinRegistryPort

__all__ = ["TwinRegistry"]


class TwinRegistry(TwinRegistryPort):
    """Thread-safe registry for Digital Twin versions and capabilities."""

    def __init__(
        self,
        builder_name: str = "default-twin-builder",
        builder_version_str: str = "1.0.0",
        schema_version_str: str = "1.0.0",
        twin_version_str: str = "1.0.0",
    ) -> None:
        self._builder_name = builder_name
        self._version = TwinVersion(
            twin_version=twin_version_str,
            schema_version=schema_version_str,
            builder_version=builder_version_str,
        )
        self._capabilities: FrozenSet[str] = frozenset(
            {
                "repository_twin",
                "snapshot_manager",
                "synchronization_engine",
                "incremental_updates",
                "consistency_validation",
                "repository_metrics",
                "twin_persistence",
            }
        )

    def builder_version(self) -> ComponentVersion:
        """Return ComponentVersion of the twin builder."""
        return ComponentVersion(
            name=self._builder_name, version=self._version.builder_version
        )

    def twin_version(self) -> TwinVersion:
        """Return full TwinVersion object."""
        return self._version

    def supported_capabilities(self) -> FrozenSet[str]:
        """Return supported capabilities set."""
        return self._capabilities
