"""Repository Knowledge Graph Navigator Service.

Facilitates high-performance traversals and query operations over the unified
Repository Knowledge Graph, hiding all NetworkX details inside the implementation.
"""

import logging
from typing import Any, Dict, List, Optional
import networkx as nx

from models.knowledge_graph import KnowledgeGraphNode

logger = logging.getLogger(__name__)


class RepositoryKnowledgeGraphNavigator:
    """Query, navigation, and traversal façade over the Repository Knowledge Graph."""

    def __init__(self, builder: Optional[Any] = None) -> None:
        """Initialise the navigator service."""
        self.builder = builder

    def get_builder(self) -> Any:
        """Lazily resolve the builder to prevent process-startup circular dependency issues."""
        if self.builder is None:
            from backend.dependencies import repository_knowledge_graph_builder

            self.builder = repository_knowledge_graph_builder
        return self.builder

    def _get_node_as_dto(
        self, graph: nx.DiGraph, node_id: str
    ) -> Optional[KnowledgeGraphNode]:
        """Convert a NetworkX node to its Pydantic Node DTO."""
        if node_id not in graph:
            return None
        data = graph.nodes[node_id]
        node_type = data.get("type", "unknown")
        props = {k: v for k, v in data.items() if k != "type"}
        return KnowledgeGraphNode(id=node_id, type=node_type, properties=props)

    def find_node(self, repo_name: str, node_id: str) -> Optional[KnowledgeGraphNode]:
        """Finds and returns a specific node in the Knowledge Graph by its stable ID."""
        builder = self.get_builder()
        nx_graph = builder.build_networkx_graph(repo_name)
        return self._get_node_as_dto(nx_graph, node_id)

    def find_neighbors(
        self, repo_name: str, node_id: str, edge_type: Optional[str] = None
    ) -> List[KnowledgeGraphNode]:
        """Finds immediate successor and predecessor neighbor nodes, optionally filtering by relationship type."""
        builder = self.get_builder()
        nx_graph = builder.build_networkx_graph(repo_name)

        if node_id not in nx_graph:
            return []

        neighbors = []
        # Predecessors (incoming edges)
        for pred in nx_graph.predecessors(node_id):
            if edge_type:
                edge_data = nx_graph.get_edge_data(pred, node_id)
                if edge_data and edge_data.get("type") != edge_type:
                    continue
            neighbors.append(pred)

        # Successors (outgoing edges)
        for succ in nx_graph.successors(node_id):
            if edge_type:
                edge_data = nx_graph.get_edge_data(node_id, succ)
                if edge_data and edge_data.get("type") != edge_type:
                    continue
            neighbors.append(succ)

        # Convert unique IDs back to DTOs
        unique_neighbors = list(set(neighbors))
        return [
            self._get_node_as_dto(nx_graph, nid)
            for nid in unique_neighbors
            if nid in nx_graph
        ]

    def find_path(self, repo_name: str, source: str, target: str) -> List[str]:
        """Finds any path of node IDs connecting source and target nodes."""
        builder = self.get_builder()
        nx_graph = builder.build_networkx_graph(repo_name)

        try:
            # nx.all_simple_paths returns a generator, we take the first one
            paths_gen = nx.all_simple_paths(nx_graph, source, target)
            return next(paths_gen, [])
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []
        except Exception as e:
            logger.debug("Failed to find path from %s to %s: %s", source, target, e)
            return []

    def find_shortest_path(self, repo_name: str, source: str, target: str) -> List[str]:
        """Finds the shortest sequence of node IDs connecting source and target nodes."""
        builder = self.get_builder()
        nx_graph = builder.build_networkx_graph(repo_name)

        try:
            return nx.shortest_path(nx_graph, source, target)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []
        except Exception as e:
            logger.debug(
                "Failed to find shortest path from %s to %s: %s", source, target, e
            )
            return []

    def find_cycles(self, repo_name: str) -> List[List[str]]:
        """Detects and returns all cycles (loops) present in the Knowledge Graph."""
        builder = self.get_builder()
        nx_graph = builder.build_networkx_graph(repo_name)

        try:
            return list(nx.simple_cycles(nx_graph))
        except Exception as e:
            logger.debug("Simple cycles detection failed: %s", e)
            return []

    def find_impact(self, repo_name: str, node_id: str) -> List[str]:
        """Returns the list of all downstream node IDs affected by the specified node ( blast radius )."""
        builder = self.get_builder()
        nx_graph = builder.build_networkx_graph(repo_name)

        if node_id not in nx_graph:
            return []

        try:
            # Transitively affected successor nodes using BFS
            affected = list(nx.descendants(nx_graph, node_id))
            return affected
        except Exception as e:
            logger.debug("Transitive descendants lookup failed for %s: %s", node_id, e)
            return []

    def find_entrypoints(self, repo_name: str) -> List[KnowledgeGraphNode]:
        """Identifies and returns entrypoint file or symbol nodes (in-degree == 0)."""
        builder = self.get_builder()
        nx_graph = builder.build_networkx_graph(repo_name)

        entrypoint_ids = [
            node_id for node_id, in_degree in nx_graph.in_degree() if in_degree == 0
        ]
        # Filter for file/symbol types specifically to avoid report/repo root clutter
        res = []
        for nid in entrypoint_ids:
            dto = self._get_node_as_dto(nx_graph, nid)
            if dto and dto.type in {"file", "symbol"}:
                res.append(dto)
        return res

    def extract_subgraph(
        self,
        repo_name: str,
        root_entities: List[str],
        max_depth: int = 3,
        edge_types: Optional[List[str]] = None,
        max_nodes: int = 100,
        max_edges: int = 500,
        relationship_filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Extracts a semantic subgraph slice from the unified Knowledge Graph.

        Performs BFS starting from root_entities up to max_depth.
        Returns a dict of serialized nodes and edges.
        """
        builder = self.get_builder()
        nx_graph = builder.build_networkx_graph(repo_name)

        # BFS Queue: (node_id, current_depth)
        queue = [(root, 0) for root in root_entities if root in nx_graph]
        visited_nodes = {root for root, _ in queue}
        visited_edges = set()

        while queue:
            node_id, depth = queue.pop(0)
            if len(visited_nodes) >= max_nodes:
                break
            if depth >= max_depth:
                continue

            # Outgoing neighbors (successors)
            for succ in nx_graph.successors(node_id):
                edge_data = nx_graph.get_edge_data(node_id, succ)
                edge_type = edge_data.get("type") if edge_data else None
                if edge_types and edge_type not in edge_types:
                    continue

                if len(visited_edges) < max_edges:
                    visited_edges.add((node_id, succ, edge_type))
                    if succ not in visited_nodes and len(visited_nodes) < max_nodes:
                        visited_nodes.add(succ)
                        queue.append((succ, depth + 1))

            # Incoming neighbors (predecessors)
            for pred in nx_graph.predecessors(node_id):
                edge_data = nx_graph.get_edge_data(pred, node_id)
                edge_type = edge_data.get("type") if edge_data else None
                if edge_types and edge_type not in edge_types:
                    continue

                if len(visited_edges) < max_edges:
                    visited_edges.add((pred, node_id, edge_type))
                    if pred not in visited_nodes and len(visited_nodes) < max_nodes:
                        visited_nodes.add(pred)
                        queue.append((pred, depth + 1))

        # Build output structure
        nodes = []
        for nid in visited_nodes:
            dto = self._get_node_as_dto(nx_graph, nid)
            if dto:
                nodes.append(dto.model_dump())

        edges = []
        for u, v, etype in visited_edges:
            edges.append(
                {"source": u, "target": v, "type": etype or "unknown", "properties": {}}
            )

        return {"nodes": nodes, "edges": edges}
