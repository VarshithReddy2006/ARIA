"""Graph Serializer Service — PH2-001 Interactive Dependency Graph.

Provides fast, focused graph queries on top of the persisted NetworkX DiGraph.
All methods load the graph from the persisted graph storage (GraphService.load_graph) and
return React-Flow-compatible dicts.

Four query modes:
  full        → full graph (priority-sorted with _MAX_NODES cap) or search-filtered subgraph
  neighbors   → immediate predecessors + successors of one node
  trace       → full forward or reverse BFS from one node up to max_depth hops
  search      → subgraph containing all nodes whose path/label matches a query

None of these methods write to disk or modify the graph.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Set

import networkx as nx

from services.graph_service import GraphService
from services.architecture_service import ArchitectureService

logger = logging.getLogger(__name__)

# Maximum BFS depth for trace queries
_DEFAULT_TRACE_DEPTH = 6
# Maximum nodes returned by any single query (safety cap)
_MAX_NODES = 500
_MAX_EDGES = 2000


class GraphSerializer:
    """Converts NetworkX graph subsets into React-Flow-compatible JSON."""

    def __init__(
        self,
        graph_service: Optional[GraphService] = None,
        architecture_service: Optional[ArchitectureService] = None,
    ) -> None:
        self.graph_service = graph_service or GraphService()
        self.architecture_service = architecture_service or ArchitectureService()
        self._graph_cache: Dict[str, nx.DiGraph] = {}

    def clear_cache(self, repo_name: Optional[str] = None) -> None:
        """Clear the in-memory graph cache."""
        if repo_name:
            self._graph_cache.pop(repo_name, None)
        else:
            self._graph_cache.clear()

    # ------------------------------------------------------------------
    # Public query methods
    # ------------------------------------------------------------------

    def get_full_graph(
        self,
        repo_name: str,
        search_query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return the full (or search-filtered) graph for a repository.

        Uses the internal _serialise path so every node carries the complete
        8-field schema: id, label, category, degree, centrality, language,
        highlighted, is_focus.

        If *search_query* is provided, only matching nodes (plus their immediate
        neighbours) are included; matching nodes are flagged highlighted=True.
        If no query is given the full graph is returned, capped at _MAX_NODES
        with highest-priority nodes (entry points, core modules) kept first.
        """
        graph = self._load(repo_name)
        if graph is None:
            return self._error("Graph not found for this repository.")

        if graph.number_of_nodes() == 0:
            return {
                "nodes": [],
                "edges": [],
                "node_count": 0,
                "edge_count": 0,
            }

        summary = self.architecture_service.get_summary(repo_name)
        cat_sets = self._category_sets(summary)

        # ── Search-filtered path ──────────────────────────────────────
        if search_query and search_query.strip():
            q = search_query.strip().lower()
            matching: Set[str] = {
                n
                for n in graph.nodes()
                if q in n.lower() or q in os.path.basename(n).lower()
            }
            # Include immediate neighbours for context
            context: Set[str] = set(matching)
            for m in matching:
                context.update(graph.predecessors(m))
                context.update(graph.successors(m))
            if len(context) > _MAX_NODES:
                excess = context - matching
                context = matching | set(list(excess)[: _MAX_NODES - len(matching)])
            subgraph = graph.subgraph(context)
            result = self._serialise(
                subgraph,
                cat_sets=cat_sets,
                focus_node=None,
                highlighted_nodes=matching,
            )
            result["matched_count"] = len(matching)
            result["query"] = search_query
            return result

        # ── Full graph path — apply priority-sorted _MAX_NODES cap ────
        cat_priority = {
            "entry_point": 4,
            "core_module": 3,
            "high_coupling": 2,
            "directory": 1,
            "regular": 0,
        }
        if graph.number_of_nodes() > 1:
            try:
                centrality: Dict[str, float] = nx.degree_centrality(graph)
            except Exception:
                centrality = {n: 0.0 for n in graph.nodes()}
        else:
            centrality = {n: 0.0 for n in graph.nodes()}
        degrees = dict(graph.degree())

        def _priority(n: str) -> tuple:
            cat = self._categorise(n, cat_sets)
            return (cat_priority.get(cat, 0), centrality.get(n, 0.0), degrees.get(n, 0))

        sorted_nodes = sorted(graph.nodes(), key=_priority, reverse=True)
        top_nodes = sorted_nodes[:_MAX_NODES]
        subgraph = graph.subgraph(top_nodes)
        return self._serialise(
            subgraph,
            cat_sets=cat_sets,
            focus_node=None,
            highlighted_nodes=set(),
        )

    def get_neighbors(
        self,
        repo_name: str,
        node_id: str,
    ) -> Dict[str, Any]:
        """Return the immediate neighborhood of *node_id*.

        Returns the focal node plus all direct predecessors (files that import
        it) and successors (files it imports), together with the edges between
        them.  The focal node is flagged as category='focus'.

        Args:
            repo_name: Repository identifier (owner/repo).
            node_id:   The file path acting as the focal node.

        Returns:
            React-Flow compatible {nodes, edges} dict.
            Returns {nodes: [], edges: [], error: "..."} on bad input.
        """
        graph = self._load(repo_name)
        if graph is None:
            return self._error("Graph not found for repository.")
        if node_id not in graph:
            return self._error(f"Node '{node_id}' not found in graph.")

        summary = self.architecture_service.get_summary(repo_name)
        cat_sets = self._category_sets(summary)

        neighbor_ids: Set[str] = set()
        neighbor_ids.add(node_id)
        neighbor_ids.update(graph.predecessors(node_id))
        neighbor_ids.update(graph.successors(node_id))

        subgraph = graph.subgraph(neighbor_ids)
        return self._serialise(
            subgraph,
            cat_sets=cat_sets,
            focus_node=node_id,
            highlighted_nodes=neighbor_ids - {node_id},
        )

    def get_trace(
        self,
        repo_name: str,
        node_id: str,
        direction: str = "both",
        max_depth: int = _DEFAULT_TRACE_DEPTH,
    ) -> Dict[str, Any]:
        """Return all nodes reachable from *node_id* by BFS up to *max_depth*.

        Args:
            repo_name:  Repository identifier (owner/repo).
            node_id:    The starting file path.
            direction:  'forward'  → files this node imports (what it depends on)
                        'backward' → files that import this node (dependants)
                        'both'     → both directions
            max_depth:  Maximum BFS hop count.

        Returns:
            React-Flow compatible {nodes, edges} dict.
        """
        graph = self._load(repo_name)
        if graph is None:
            return self._error("Graph not found for repository.")
        if node_id not in graph:
            return self._error(f"Node '{node_id}' not found in graph.")

        summary = self.architecture_service.get_summary(repo_name)
        cat_sets = self._category_sets(summary)

        reachable: Set[str] = {node_id}
        highlighted: Set[str] = set()

        if direction in ("forward", "both"):
            fwd = self._bfs(graph, node_id, forward=True, max_depth=max_depth)
            reachable.update(fwd)
            highlighted.update(fwd)

        if direction in ("backward", "both"):
            bwd = self._bfs(graph, node_id, forward=False, max_depth=max_depth)
            reachable.update(bwd)
            highlighted.update(bwd)

        # Cap to _MAX_NODES keeping focus + highlighted first
        if len(reachable) > _MAX_NODES:
            priority = [node_id] + list(highlighted)[: _MAX_NODES - 1]
            reachable = set(priority)

        subgraph = graph.subgraph(reachable)
        return self._serialise(
            subgraph,
            cat_sets=cat_sets,
            focus_node=node_id,
            highlighted_nodes=highlighted,
        )

    def get_search(
        self,
        repo_name: str,
        query: str,
    ) -> Dict[str, Any]:
        """Return a subgraph of nodes whose path or label matches *query*.

        The returned graph contains matching nodes plus their immediate
        neighbours (one hop) so the user can see context. Matching nodes
        are flagged as highlighted.

        Args:
            repo_name: Repository identifier (owner/repo).
            query:     Case-insensitive substring to match against file paths.

        Returns:
            React-Flow compatible {nodes, edges, matched_count} dict.
        """
        if not query or not query.strip():
            return self.get_full_graph(repo_name)

        graph = self._load(repo_name)
        if graph is None:
            return self._error("Graph not found for repository.")

        summary = self.architecture_service.get_summary(repo_name)
        cat_sets = self._category_sets(summary)

        q = query.strip().lower()
        matching: Set[str] = set()
        for node in graph.nodes():
            label = os.path.basename(node).lower()
            if q in node.lower() or q in label:
                matching.add(node)

        # Include immediate neighbours for context
        context: Set[str] = set(matching)
        for m in matching:
            context.update(graph.predecessors(m))
            context.update(graph.successors(m))

        # Cap
        if len(context) > _MAX_NODES:
            # Prioritise matching nodes
            excess = context - matching
            context = matching | set(list(excess)[: _MAX_NODES - len(matching)])

        subgraph = graph.subgraph(context)
        result = self._serialise(
            subgraph,
            cat_sets=cat_sets,
            focus_node=None,
            highlighted_nodes=matching,
        )
        result["matched_count"] = len(matching)
        result["query"] = query
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self, repo_name: str) -> Optional[nx.DiGraph]:
        if repo_name in self._graph_cache:
            return self._graph_cache[repo_name]
        graph = self.graph_service.load_graph(repo_name)
        if graph is None:
            logger.warning("GraphSerializer: missing graph for '%s'", repo_name)
            return None
        self._graph_cache[repo_name] = graph
        return graph
        return graph

    @staticmethod
    def _bfs(
        graph: nx.DiGraph,
        start: str,
        forward: bool,
        max_depth: int,
    ) -> Set[str]:
        """Simple iterative BFS."""
        visited: Set[str] = set()
        queue = [(start, 0)]
        while queue:
            node, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            neighbours = (
                list(graph.successors(node))
                if forward
                else list(graph.predecessors(node))
            )
            for nb in neighbours:
                if nb not in visited and nb != start:
                    visited.add(nb)
                    queue.append((nb, depth + 1))
        return visited

    @staticmethod
    def _category_sets(summary) -> Dict[str, Set[str]]:
        if summary is None:
            return {"entry": set(), "core": set(), "coupling": set()}
        return {
            "entry": set(summary.entry_points or []),
            "core": set(summary.core_modules or []),
            "coupling": set(summary.high_coupling_modules or []),
        }

    @staticmethod
    def _categorise(node_id: str, cat_sets: Dict[str, Set[str]]) -> str:
        if node_id in cat_sets["entry"]:
            return "entry_point"
        if node_id in cat_sets["core"]:
            return "core_module"
        if node_id in cat_sets["coupling"]:
            return "high_coupling"
        norm = node_id.replace("\\", "/").lower()
        if norm.startswith(("tests/", "docs/", "examples/")):
            return "directory"
        return "regular"

    def _serialise(
        self,
        subgraph: nx.DiGraph,
        cat_sets: Dict[str, Set[str]],
        focus_node: Optional[str],
        highlighted_nodes: Set[str],
    ) -> Dict[str, Any]:
        """Convert a NetworkX subgraph to React-Flow-compatible JSON."""
        node_degrees = dict(subgraph.degree())
        node_centrality: Dict[str, float] = {}
        if subgraph.number_of_nodes() > 1:
            try:
                node_centrality = nx.degree_centrality(subgraph)
            except Exception:
                node_centrality = {n: 0.0 for n in subgraph.nodes()}
        else:
            node_centrality = {n: 0.0 for n in subgraph.nodes()}

        res_nodes: List[Dict[str, Any]] = []
        for n in subgraph.nodes():
            attrs = subgraph.nodes[n]
            cat = self._categorise(n, cat_sets)
            if n == focus_node:
                cat = "focus"

            res_nodes.append(
                {
                    "id": n,
                    "label": attrs.get("label", os.path.basename(n)),
                    "category": cat,
                    "degree": node_degrees.get(n, 0),
                    "centrality": round(node_centrality.get(n, 0.0), 4),
                    "language": attrs.get("language", "unknown"),
                    "highlighted": n in highlighted_nodes,
                    "is_focus": n == focus_node,
                }
            )

        res_edges: List[Dict[str, Any]] = []
        edge_count = 0
        for u, v, eattrs in subgraph.edges(data=True):
            if edge_count >= _MAX_EDGES:
                break
            res_edges.append(
                {
                    "source": u,
                    "target": v,
                    "relationship": eattrs.get("relationship", "imports"),
                }
            )
            edge_count += 1

        return {
            "nodes": res_nodes,
            "edges": res_edges,
            "node_count": subgraph.number_of_nodes(),
            "edge_count": subgraph.number_of_edges(),
        }

    @staticmethod
    def _error(msg: str) -> Dict[str, Any]:
        return {
            "nodes": [],
            "edges": [],
            "error": msg,
            "node_count": 0,
            "edge_count": 0,
        }
