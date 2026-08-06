"""Graph Registry application service.

Tracks graph versions, schema versions, builder versions, and supported node/edge types.
Implements :class:`~ria.ports.graph.GraphRegistryPort`.
"""

from __future__ import annotations

from typing import FrozenSet

from ria.domain.enums import EdgeKind, NodeKind
from ria.domain.models.parser_identity import ComponentVersion
from ria.ports.graph import GraphRegistryPort

__all__ = ["GraphRegistry"]


class GraphRegistry(GraphRegistryPort):
    """Thread-safe registry tracking graph schema metadata and supported capabilities."""

    def __init__(
        self,
        builder_name: str = "default-graph-builder",
        builder_version: str = "1.0.0",
        schema_version: str = "1.0.0",
    ) -> None:
        self._name = builder_name
        self._version = builder_version
        self._schema_version = schema_version

    def supported_node_kinds(self) -> FrozenSet[NodeKind]:
        """Return all supported NodeKind members."""
        return frozenset(NodeKind)

    def supported_edge_kinds(self) -> FrozenSet[EdgeKind]:
        """Return all supported EdgeKind members."""
        return frozenset(EdgeKind)

    def builder_version(self) -> ComponentVersion:
        """Return ComponentVersion of the graph builder."""
        return ComponentVersion(name=self._name, version=self._version)

    @property
    def schema_version(self) -> str:
        """Return current graph schema version string."""
        return self._schema_version
