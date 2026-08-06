"""Graph Builder Service application service.

Orchestrates complete Graph construction and incremental updates.
Implements :class:`~ria.ports.graph.GraphBuilderPort`.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from ria.application.graph_edge_builder import EdgeBuilderService
from ria.application.graph_node_builder import NodeBuilderService
from ria.application.graph_update_service import GraphUpdateService
from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.change_set import ChangeSet
from ria.domain.models.file_unit import FileUnit
from ria.domain.models.graph import Graph
from ria.domain.models.graph_edge import GraphEdge
from ria.domain.models.graph_identity import GraphCacheKey, GraphFingerprint
from ria.domain.models.graph_node import GraphNode
from ria.domain.models.graph_result import GraphMetadata, GraphStatistics
from ria.domain.models.graph_snapshot import GraphSnapshot
from ria.domain.models.semantic_result import ResolutionResult
from ria.ports.graph import GraphBuilderPort, GraphCacheStore

__all__ = ["GraphBuilderService"]


class GraphBuilderService(GraphBuilderPort):
    """High-level service orchestrating Graph construction."""

    def __init__(
        self,
        cache_store: Optional[GraphCacheStore] = None,
        builder_version: str = "1.0.0",
        schema_version: str = "1.0.0",
    ) -> None:
        self._cache_store = cache_store
        self._version = builder_version
        self._schema_version = schema_version
        self._node_builder = NodeBuilderService()
        self._edge_builder = EdgeBuilderService()
        self._update_service = GraphUpdateService()

    def build_graph(
        self,
        repository_id: RepositoryId,
        commit_sha: CommitSha,
        file_units: Sequence[FileUnit],
        resolution_results: Sequence[ResolutionResult],
    ) -> GraphSnapshot:
        """Construct a complete GraphSnapshot for a repository commit."""
        fp = GraphFingerprint(
            builder_name="default-graph-builder",
            builder_version=self._version,
            schema_version=self._schema_version,
        )
        cache_key = GraphCacheKey(commit_sha=commit_sha, fingerprint=fp)

        # 1. Check cache
        if self._cache_store is not None:
            cached = self._cache_store.get(cache_key)
            if cached is not None:
                return cached

        # 2. Build Repository & Commit nodes
        nodes: List[GraphNode] = [
            self._node_builder.build_repository_node(repository_id),
            self._node_builder.build_commit_node(repository_id, commit_sha),
        ]

        # 3. Build File nodes and Symbol nodes
        edges: List[GraphEdge] = []
        for unit in file_units:
            file_node = self._node_builder.build_file_node(repository_id, unit)
            nodes.append(file_node)

        for res in resolution_results:
            sym_nodes = self._node_builder.build_symbol_nodes(
                repository_id, res.symbols
            )
            scope_nodes = [
                self._node_builder.build_scope_node(repository_id, sc)
                for sc in res.scopes
            ]
            nodes.extend(sym_nodes)
            nodes.extend(scope_nodes)

            # Build edges for this resolution result
            res_edges = self._edge_builder.build_edges(nodes, res)
            edges.extend(res_edges)

        # 4. Construct Graph
        graph = Graph(nodes=tuple(nodes), edges=tuple(edges))
        metadata = GraphMetadata(
            repository_id=repository_id.value,
            commit_sha=commit_sha.value,
            builder_version=self._version,
            schema_version=self._schema_version,
        )
        statistics = GraphStatistics(
            nodes_total=len(nodes),
            edges_total=len(edges),
        )

        snapshot = GraphSnapshot(
            repository_id=repository_id,
            commit_sha=commit_sha,
            graph=graph,
            fingerprint=fp,
            metadata=metadata,
            statistics=statistics,
        )

        # 5. Store in cache if present
        if self._cache_store is not None:
            self._cache_store.put(cache_key, snapshot)

        return snapshot

    def update_graph(
        self,
        previous_snapshot: GraphSnapshot,
        change_set: ChangeSet,
        updated_units: Sequence[FileUnit],
        updated_resolutions: Sequence[ResolutionResult],
    ) -> GraphSnapshot:
        """Incrementally update a GraphSnapshot."""
        new_nodes: List[GraphNode] = []
        new_edges: List[GraphEdge] = []

        repo_id = previous_snapshot.repository_id
        for unit in updated_units:
            new_nodes.append(self._node_builder.build_file_node(repo_id, unit))

        for res in updated_resolutions:
            sym_nodes = self._node_builder.build_symbol_nodes(repo_id, res.symbols)
            scope_nodes = [
                self._node_builder.build_scope_node(repo_id, sc) for sc in res.scopes
            ]
            new_nodes.extend(sym_nodes)
            new_nodes.extend(scope_nodes)

            res_edges = self._edge_builder.build_edges(new_nodes, res)
            new_edges.extend(res_edges)

        return self._update_service.incremental_update(
            previous_snapshot=previous_snapshot,
            new_commit_sha=CommitSha(change_set.head_sha),
            change_set=change_set,
            new_nodes=new_nodes,
            new_edges=new_edges,
        )
