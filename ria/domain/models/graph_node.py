"""GraphNode domain entity.

Represents a single vertex/node in the Repository Knowledge Graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from ria.domain.enums import NodeKind
from ria.domain.models.graph_node_id import GraphNodeId
from ria.domain.models.scope_id import ScopeId
from ria.domain.models.span import SourceSpan
from ria.domain.models.symbol_id import SymbolId

__all__ = ["GraphNode"]


@dataclass(frozen=True)
class GraphNode:
    """Immutable vertex in the Repository Knowledge Graph.

    Attributes:
        node_id: Unique GraphNodeId.
        kind: NodeKind classification.
        name: Short human-readable or entity name.
        qualified_name: Fully qualified domain moniker (if applicable).
        location_path: Repository-relative file path (if applicable).
        span: Source byte span (if applicable).
        symbol_id: Bound SymbolId (if representing a symbol).
        scope_id: Bound ScopeId (if representing a lexical scope).
        properties: Immutable mapping of additional node properties.
    """

    node_id: GraphNodeId
    kind: NodeKind
    name: str
    qualified_name: Optional[str] = None
    location_path: Optional[str] = None
    span: Optional[SourceSpan] = None
    symbol_id: Optional[SymbolId] = None
    scope_id: Optional[ScopeId] = None
    properties: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("GraphNode name must be a non-empty string")
