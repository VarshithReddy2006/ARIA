"""Incremental Graph Update application service.

Computes incremental graph updates consuming a ChangeSet and re-building only affected nodes and edges.
"""

from __future__ import annotations

from typing import Dict, List, Sequence, Set, Tuple

from ria.domain.identity import CommitSha
from ria.domain.models.change_set import ChangeSet
from ria.domain.models.graph import Graph
from ria.domain.models.graph_edge import GraphEdge
from ria.domain.models.graph_edge_id import GraphEdgeId
from ria.domain.models.graph_node import GraphNode
from ria.domain.models.graph_node_id import GraphNodeId
from ria.domain.models.graph_result import GraphMetadata, GraphStatistics
from ria.domain.models.graph_snapshot import GraphSnapshot

__all__ = ["GraphUpdateService"]


class GraphUpdateService:
    """Service for incrementally updating a GraphSnapshot from a previous snapshot and ChangeSet."""

    def incremental_update(
        self,
        previous_snapshot: GraphSnapshot,
        new_commit_sha: CommitSha,
        change_set: ChangeSet,
        new_nodes: Sequence[GraphNode],
        new_edges: Sequence[GraphEdge],
    ) -> GraphSnapshot:
        """Produce a new GraphSnapshot by performing incremental node and edge replacement.

        Args:
            previous_snapshot: The baseline GraphSnapshot.
            new_commit_sha: New target CommitSha.
            change_set: ChangeSet indicating deleted, modified, and added paths.
            new_nodes: Newly constructed nodes for added/modified files.
            new_edges: Newly constructed edges for added/modified files.

        Returns:
            Incrementally updated GraphSnapshot.
        """
        affected_paths: Set[str] = set(change_set.deleted) | set(change_set.modified)

        # Retain nodes from previous graph whose location_path is not affected
        retained_nodes: List[GraphNode] = []
        retained_node_ids: Set[GraphNodeId] = set()

        for node in previous_snapshot.graph.nodes:
            if node.location_path not in affected_paths:
                retained_nodes.append(node)
                retained_node_ids.add(node.node_id)

        # Merge new nodes
        for node in new_nodes:
            retained_nodes.append(node)
            retained_node_ids.add(node.node_id)

        # Deduplicate nodes by node_id
        unique_node_map: Dict[GraphNodeId, GraphNode] = {
            n.node_id: n for n in retained_nodes
        }
        final_nodes: Tuple[GraphNode, ...] = tuple(unique_node_map.values())
        valid_node_ids = set(unique_node_map.keys())

        # Retain edges connecting valid retained nodes
        retained_edges: List[GraphEdge] = []
        for edge in previous_snapshot.graph.edges:
            if edge.source_id in valid_node_ids and edge.target_id in valid_node_ids:
                retained_edges.append(edge)

        # Add new edges connecting valid nodes
        for edge in new_edges:
            if edge.source_id in valid_node_ids and edge.target_id in valid_node_ids:
                retained_edges.append(edge)

        # Deduplicate edges by edge_id
        unique_edge_map: Dict[GraphEdgeId, GraphEdge] = {
            e.edge_id: e for e in retained_edges
        }
        final_edges: Tuple[GraphEdge, ...] = tuple(unique_edge_map.values())

        updated_graph = Graph(nodes=final_nodes, edges=final_edges)

        metadata = GraphMetadata(
            repository_id=previous_snapshot.repository_id.value,
            commit_sha=new_commit_sha.value,
            builder_version=previous_snapshot.fingerprint.builder_version,
            schema_version=previous_snapshot.fingerprint.schema_version,
        )

        statistics = GraphStatistics(
            nodes_total=len(final_nodes),
            edges_total=len(final_edges),
        )

        return GraphSnapshot(
            repository_id=previous_snapshot.repository_id,
            commit_sha=new_commit_sha,
            graph=updated_graph,
            fingerprint=previous_snapshot.fingerprint,
            metadata=metadata,
            statistics=statistics,
        )
