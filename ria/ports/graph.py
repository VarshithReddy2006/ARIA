"""Port protocols for Milestone 5 — Repository Knowledge Graph.

Defines runtime checkable protocols for graph construction, traversal, querying,
registry, caching, and persistence.
"""

from __future__ import annotations

from typing import FrozenSet, Optional, Protocol, Sequence, Tuple, runtime_checkable

from ria.domain.enums import EdgeKind, NodeKind
from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.change_set import ChangeSet
from ria.domain.models.file_unit import FileUnit
from ria.domain.models.graph import Graph
from ria.domain.models.graph_edge import GraphEdge
from ria.domain.models.graph_identity import GraphCacheKey
from ria.domain.models.graph_node import GraphNode
from ria.domain.models.graph_node_id import GraphNodeId
from ria.domain.models.graph_result import TraversalResult
from ria.domain.models.graph_snapshot import GraphSnapshot
from ria.domain.models.parser_identity import ComponentVersion
from ria.domain.models.relationship import Relationship
from ria.domain.models.semantic_result import ResolutionResult
from ria.domain.models.symbol import Symbol
from ria.domain.models.symbol_id import SymbolId

__all__ = [
    "NodeBuilderPort",
    "EdgeBuilderPort",
    "GraphBuilderPort",
    "TraversalPort",
    "GraphQueryPort",
    "GraphStorePort",
    "GraphRegistryPort",
    "GraphCacheStore",
]


@runtime_checkable
class NodeBuilderPort(Protocol):
    """Port for generating GraphNode entities from repository and semantic facts."""

    def build_repository_node(self, repository_id: RepositoryId) -> GraphNode:
        """Build a Repository level graph node."""
        ...

    def build_commit_node(
        self, repository_id: RepositoryId, commit_sha: CommitSha
    ) -> GraphNode:
        """Build a Commit level graph node."""
        ...

    def build_file_node(self, repository_id: RepositoryId, unit: FileUnit) -> GraphNode:
        """Build a File/Module graph node."""
        ...

    def build_symbol_nodes(
        self,
        repository_id: RepositoryId,
        symbols: Sequence[Symbol],
    ) -> Tuple[GraphNode, ...]:
        """Build Symbol/Class/Method/Function graph nodes."""
        ...


@runtime_checkable
class EdgeBuilderPort(Protocol):
    """Port for generating GraphEdge entities connecting nodes."""

    def build_edges(
        self,
        nodes: Sequence[GraphNode],
        resolution_result: ResolutionResult,
    ) -> Tuple[GraphEdge, ...]:
        """Build directed GraphEdge entities from semantic resolution results."""
        ...


@runtime_checkable
class GraphBuilderPort(Protocol):
    """Port for building complete Graph snapshots from repository semantic facts."""

    def build_graph(
        self,
        repository_id: RepositoryId,
        commit_sha: CommitSha,
        file_units: Sequence[FileUnit],
        resolution_results: Sequence[ResolutionResult],
    ) -> GraphSnapshot:
        """Construct a complete GraphSnapshot."""
        ...

    def update_graph(
        self,
        previous_snapshot: GraphSnapshot,
        change_set: ChangeSet,
        updated_units: Sequence[FileUnit],
        updated_resolutions: Sequence[ResolutionResult],
    ) -> GraphSnapshot:
        """Incrementally update a graph snapshot based on a ChangeSet."""
        ...


@runtime_checkable
class TraversalPort(Protocol):
    """Port for executing deterministic graph traversal algorithms."""

    def breadth_first(
        self,
        graph: Graph,
        start_id: GraphNodeId,
        max_depth: Optional[int] = None,
    ) -> TraversalResult:
        """Execute breadth-first search traversal."""
        ...

    def depth_first(
        self,
        graph: Graph,
        start_id: GraphNodeId,
        max_depth: Optional[int] = None,
    ) -> TraversalResult:
        """Execute depth-first search traversal."""
        ...

    def shortest_path(
        self,
        graph: Graph,
        start_id: GraphNodeId,
        target_id: GraphNodeId,
    ) -> TraversalResult:
        """Compute shortest path between start_id and target_id."""
        ...

    def reachability(
        self,
        graph: Graph,
        start_id: GraphNodeId,
        target_id: GraphNodeId,
    ) -> bool:
        """Check if target_id is reachable from start_id."""
        ...


@runtime_checkable
class GraphQueryPort(Protocol):
    """Port for querying nodes, edges, relationships, and subgraphs."""

    def find_node(self, graph: Graph, node_id: GraphNodeId) -> Optional[GraphNode]:
        """Look up a node by node_id."""
        ...

    def find_symbol_node(
        self, graph: Graph, symbol_id: SymbolId
    ) -> Optional[GraphNode]:
        """Look up a node by bound SymbolId."""
        ...

    def neighbors(
        self,
        graph: Graph,
        node_id: GraphNodeId,
        edge_kind: Optional[EdgeKind] = None,
    ) -> Tuple[GraphNode, ...]:
        """Return adjacent neighbor nodes."""
        ...

    def incoming_relationships(
        self,
        graph: Graph,
        node_id: GraphNodeId,
    ) -> Tuple[Relationship, ...]:
        """Return incoming Relationship tuples."""
        ...

    def outgoing_relationships(
        self,
        graph: Graph,
        node_id: GraphNodeId,
    ) -> Tuple[Relationship, ...]:
        """Return outgoing Relationship tuples."""
        ...


@runtime_checkable
class GraphStorePort(Protocol):
    """Port for persisting and retrieving GraphSnapshot entities."""

    def save_snapshot(self, snapshot: GraphSnapshot) -> None:
        """Persist a GraphSnapshot."""
        ...

    def get_snapshot(
        self,
        repository_id: RepositoryId,
        commit_sha: CommitSha,
    ) -> Optional[GraphSnapshot]:
        """Retrieve a persisted GraphSnapshot."""
        ...


@runtime_checkable
class GraphRegistryPort(Protocol):
    """Port for tracking graph schema versions, builder versions, and supported relationship types."""

    def supported_node_kinds(self) -> FrozenSet[NodeKind]:
        """Return all supported NodeKinds."""
        ...

    def supported_edge_kinds(self) -> FrozenSet[EdgeKind]:
        """Return all supported EdgeKinds."""
        ...

    def builder_version(self) -> ComponentVersion:
        """Return identity and version of the graph builder."""
        ...


@runtime_checkable
class GraphCacheStore(Protocol):
    """Port for durable content-addressed caching of GraphSnapshots."""

    def get(self, key: GraphCacheKey) -> Optional[GraphSnapshot]:
        """Retrieve a cached GraphSnapshot."""
        ...

    def put(self, key: GraphCacheKey, snapshot: GraphSnapshot) -> None:
        """Cache a GraphSnapshot."""
        ...

    def invalidate_by_commit(self, commit_sha: CommitSha) -> int:
        """Invalidate cache entries for a commit."""
        ...

    def clear(self) -> None:
        """Purge all entries from the graph cache."""
        ...
