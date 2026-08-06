"""Unit tests for Phase 2 graph ports runtime conformance."""

from __future__ import annotations

from typing import FrozenSet, Optional, Sequence, Tuple

from ria.domain.enums import EdgeKind, NodeKind
from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.change_set import ChangeSet
from ria.domain.models.file_unit import FileUnit
from ria.domain.models.graph import Graph
from ria.domain.models.graph_edge import GraphEdge
from ria.domain.models.graph_identity import GraphCacheKey, GraphFingerprint
from ria.domain.models.graph_node import GraphNode
from ria.domain.models.graph_node_id import GraphNodeId
from ria.domain.models.graph_result import (
    GraphMetadata,
    GraphStatistics,
    TraversalResult,
)
from ria.domain.models.graph_snapshot import GraphSnapshot
from ria.domain.models.parser_identity import ComponentVersion
from ria.domain.models.relationship import Relationship
from ria.domain.models.semantic_result import ResolutionResult
from ria.domain.models.symbol import Symbol
from ria.domain.models.symbol_id import SymbolId
from ria.ports.graph import (
    EdgeBuilderPort,
    GraphBuilderPort,
    GraphCacheStore,
    GraphQueryPort,
    GraphRegistryPort,
    GraphStorePort,
    NodeBuilderPort,
    TraversalPort,
)


class DummyNodeBuilder:
    def build_repository_node(self, repository_id: RepositoryId) -> GraphNode:
        return GraphNode(
            node_id=GraphNodeId("gn_repo"),
            kind=NodeKind.REPOSITORY,
            name=str(repository_id),
        )

    def build_commit_node(
        self, repository_id: RepositoryId, commit_sha: CommitSha
    ) -> GraphNode:
        return GraphNode(
            node_id=GraphNodeId("gn_commit"), kind=NodeKind.COMMIT, name=str(commit_sha)
        )

    def build_file_node(self, repository_id: RepositoryId, unit: FileUnit) -> GraphNode:
        return GraphNode(
            node_id=GraphNodeId("gn_file"), kind=NodeKind.FILE, name=unit.path
        )

    def build_symbol_nodes(
        self, repository_id: RepositoryId, symbols: Sequence[Symbol]
    ) -> Tuple[GraphNode, ...]:
        return ()


class DummyEdgeBuilder:
    def build_edges(
        self, nodes: Sequence[GraphNode], resolution_result: ResolutionResult
    ) -> Tuple[GraphEdge, ...]:
        return ()


class DummyGraphBuilder:
    def build_graph(
        self,
        repository_id: RepositoryId,
        commit_sha: CommitSha,
        file_units: Sequence[FileUnit],
        resolution_results: Sequence[ResolutionResult],
    ) -> GraphSnapshot:
        fp = GraphFingerprint("dummy", "1.0.0")
        meta = GraphMetadata(str(repository_id), str(commit_sha))
        stats = GraphStatistics()
        return GraphSnapshot(repository_id, commit_sha, Graph(), fp, meta, stats)

    def update_graph(
        self,
        previous_snapshot: GraphSnapshot,
        change_set: ChangeSet,
        updated_units: Sequence[FileUnit],
        updated_resolutions: Sequence[ResolutionResult],
    ) -> GraphSnapshot:
        return previous_snapshot


class DummyTraversalService:
    def breadth_first(
        self, graph: Graph, start_id: GraphNodeId, max_depth: Optional[int] = None
    ) -> TraversalResult:
        return TraversalResult()

    def depth_first(
        self, graph: Graph, start_id: GraphNodeId, max_depth: Optional[int] = None
    ) -> TraversalResult:
        return TraversalResult()

    def shortest_path(
        self, graph: Graph, start_id: GraphNodeId, target_id: GraphNodeId
    ) -> TraversalResult:
        return TraversalResult()

    def reachability(
        self, graph: Graph, start_id: GraphNodeId, target_id: GraphNodeId
    ) -> bool:
        return False


class DummyGraphQueryService:
    def find_node(self, graph: Graph, node_id: GraphNodeId) -> Optional[GraphNode]:
        return None

    def find_symbol_node(
        self, graph: Graph, symbol_id: SymbolId
    ) -> Optional[GraphNode]:
        return None

    def neighbors(
        self, graph: Graph, node_id: GraphNodeId, edge_kind: Optional[EdgeKind] = None
    ) -> Tuple[GraphNode, ...]:
        return ()

    def incoming_relationships(
        self, graph: Graph, node_id: GraphNodeId
    ) -> Tuple[Relationship, ...]:
        return ()

    def outgoing_relationships(
        self, graph: Graph, node_id: GraphNodeId
    ) -> Tuple[Relationship, ...]:
        return ()


class DummyGraphStore:
    def save_snapshot(self, snapshot: GraphSnapshot) -> None:
        pass

    def get_snapshot(
        self, repository_id: RepositoryId, commit_sha: CommitSha
    ) -> Optional[GraphSnapshot]:
        return None


class DummyGraphRegistry:
    def supported_node_kinds(self) -> FrozenSet[NodeKind]:
        return frozenset(NodeKind)

    def supported_edge_kinds(self) -> FrozenSet[EdgeKind]:
        return frozenset(EdgeKind)

    def builder_version(self) -> ComponentVersion:
        return ComponentVersion("dummy", "1.0.0")


class DummyGraphCacheStore:
    def get(self, key: GraphCacheKey) -> Optional[GraphSnapshot]:
        return None

    def put(self, key: GraphCacheKey, snapshot: GraphSnapshot) -> None:
        pass

    def invalidate_by_commit(self, commit_sha: CommitSha) -> int:
        return 0

    def clear(self) -> None:
        pass


def test_node_builder_port_conformance() -> None:
    dummy = DummyNodeBuilder()
    assert isinstance(dummy, NodeBuilderPort)


def test_edge_builder_port_conformance() -> None:
    dummy = DummyEdgeBuilder()
    assert isinstance(dummy, EdgeBuilderPort)


def test_graph_builder_port_conformance() -> None:
    dummy = DummyGraphBuilder()
    assert isinstance(dummy, GraphBuilderPort)


def test_traversal_port_conformance() -> None:
    dummy = DummyTraversalService()
    assert isinstance(dummy, TraversalPort)


def test_graph_query_port_conformance() -> None:
    dummy = DummyGraphQueryService()
    assert isinstance(dummy, GraphQueryPort)


def test_graph_store_port_conformance() -> None:
    dummy = DummyGraphStore()
    assert isinstance(dummy, GraphStorePort)


def test_graph_registry_port_conformance() -> None:
    dummy = DummyGraphRegistry()
    assert isinstance(dummy, GraphRegistryPort)


def test_graph_cache_store_conformance() -> None:
    dummy = DummyGraphCacheStore()
    assert isinstance(dummy, GraphCacheStore)
