"""Call Graph Serializer Component.

Responsible for converting call graph structures and subgraphs into
React Flow-compatible JSON response models for REST API consumption.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Set

import networkx as nx

from services.call_graph.query_engine import CallGraphQueryEngine
from services.call_graph.store import CallGraphStore

logger = logging.getLogger(__name__)


class CallGraphSerializer:
    """Serializes NetworkX call graph instances to frontend JSON representations."""

    def __init__(
        self, store: CallGraphStore, query_engine: CallGraphQueryEngine
    ) -> None:
        self.store = store
        self.query_engine = query_engine

    def get_graph_json(
        self,
        repo_name: str,
        search_query: Optional[str] = None,
        max_nodes: int = 300,
        max_edges: int = 1000,
    ) -> Dict[str, Any]:
        """Return the call graph as React Flow-compatible JSON.

        Mirrors GraphSerializer._serialise() schema so the frontend
        InteractiveDependencyGraph component can render it unchanged.
        """
        G = self.store.load_graph(repo_name)
        if G is None:
            return {
                "nodes": [],
                "edges": [],
                "node_count": 0,
                "edge_count": 0,
                "error": "Call graph not found. Please analyze the repository first.",
            }

        # Filter by search query if provided
        if search_query and search_query.strip():
            q = search_query.lower()
            matching = {
                n
                for n in G.nodes()
                if q in G.nodes[n].get("name", "").lower()
                or q in G.nodes[n].get("qualified", "").lower()
                or q in G.nodes[n].get("file_path", "").lower()
            }
            context = set(matching)
            for m in matching:
                context.update(G.predecessors(m))
                context.update(G.successors(m))
            working = G.subgraph(context)
        else:
            # Priority sort: high fan-in first (most-called = most important)
            sorted_nodes = sorted(
                G.nodes(),
                key=lambda n: G.in_degree(n),
                reverse=True,
            )[:max_nodes]
            working = G.subgraph(sorted_nodes)

        centrality: Dict[str, float] = {}
        if working.number_of_nodes() > 1:
            try:
                centrality = nx.degree_centrality(working)
            except Exception:
                centrality = {}

        res_nodes = []
        for n in working.nodes():
            attrs = working.nodes[n]
            fi = working.in_degree(n)
            fo = working.out_degree(n)
            cat = (
                "entry_point" if fi == 0 else ("core_module" if fi >= 5 else "regular")
            )
            if attrs.get("is_recursive"):
                cat = "high_coupling"

            res_nodes.append(
                {
                    "id": n,
                    "label": attrs.get("name", n),
                    "category": cat,
                    "degree": fi + fo,
                    "centrality": round(centrality.get(n, 0.0), 4),
                    "language": attrs.get("language", "unknown"),
                    "highlighted": False,
                    "is_focus": False,
                    # Call-graph-specific extras
                    "qualified": attrs.get("qualified", ""),
                    "file_path": attrs.get("file_path", ""),
                    "fan_in": fi,
                    "fan_out": fo,
                    "is_recursive": attrs.get("is_recursive", False),
                    "parent_class": attrs.get("parent_class", ""),
                    "symbol_type": attrs.get("symbol_type", "function"),
                }
            )

        res_edges = []
        count = 0
        for u, v, eattrs in working.edges(data=True):
            if count >= max_edges:
                break
            res_edges.append(
                {
                    "source": u,
                    "target": v,
                    "relationship": "calls",
                    "ambiguous": eattrs.get("ambiguous", False),
                }
            )
            count += 1

        return {
            "nodes": res_nodes,
            "edges": res_edges,
            "node_count": working.number_of_nodes(),
            "edge_count": working.number_of_edges(),
        }

    def get_neighbors_json(self, repo_name: str, function_id: str) -> Dict[str, Any]:
        """Return immediate callers + callees as React Flow JSON."""
        G = self.store.load_graph(repo_name)
        if G is None or function_id not in G:
            return {
                "nodes": [],
                "edges": [],
                "node_count": 0,
                "edge_count": 0,
                "error": f"Function '{function_id}' not found.",
            }

        context = {function_id}
        context.update(G.predecessors(function_id))
        context.update(G.successors(function_id))
        return self.serialise_subgraph(G, context, focus_id=function_id)

    def get_trace_json(
        self,
        repo_name: str,
        function_id: str,
        direction: str = "both",
        depth: int = 6,
    ) -> Dict[str, Any]:
        """Return BFS trace from *function_id* as React Flow JSON."""
        G = self.store.load_graph(repo_name)
        if G is None or function_id not in G:
            return {
                "nodes": [],
                "edges": [],
                "node_count": 0,
                "edge_count": 0,
                "error": f"Function '{function_id}' not found.",
            }

        reachable: Set[str] = {function_id}
        highlighted: Set[str] = set()

        if direction in ("forward", "both"):
            fwd = self.query_engine.bfs(G, function_id, forward=True, max_depth=depth)
            reachable.update(fwd)
            highlighted.update(fwd)

        if direction in ("backward", "both"):
            bwd = self.query_engine.bfs(G, function_id, forward=False, max_depth=depth)
            reachable.update(bwd)
            highlighted.update(bwd)

        return self.serialise_subgraph(
            G, reachable, focus_id=function_id, highlighted=highlighted
        )

    def serialise_subgraph(
        self,
        G: nx.DiGraph,
        node_ids: Set[str],
        focus_id: Optional[str] = None,
        highlighted: Optional[Set[str]] = None,
        max_edges: int = 1000,
    ) -> Dict[str, Any]:
        """Serialise a node subset to React Flow JSON."""
        highlighted = highlighted or set()
        subgraph = G.subgraph(node_ids)

        centrality: Dict[str, float] = {}
        if subgraph.number_of_nodes() > 1:
            try:
                centrality = nx.degree_centrality(subgraph)
            except Exception:
                pass

        res_nodes = []
        for n in subgraph.nodes():
            attrs = subgraph.nodes[n]
            fi = subgraph.in_degree(n)
            fo = subgraph.out_degree(n)
            cat = (
                "focus"
                if n == focus_id
                else (
                    "entry_point"
                    if fi == 0
                    else "core_module"
                    if fi >= 5
                    else "regular"
                )
            )
            if attrs.get("is_recursive"):
                cat = "high_coupling" if n != focus_id else cat

            res_nodes.append(
                {
                    "id": n,
                    "label": attrs.get("name", n),
                    "category": cat,
                    "degree": fi + fo,
                    "centrality": round(centrality.get(n, 0.0), 4),
                    "language": attrs.get("language", "unknown"),
                    "highlighted": n in highlighted,
                    "is_focus": n == focus_id,
                    "qualified": attrs.get("qualified", ""),
                    "file_path": attrs.get("file_path", ""),
                    "fan_in": fi,
                    "fan_out": fo,
                    "is_recursive": attrs.get("is_recursive", False),
                    "parent_class": attrs.get("parent_class", ""),
                    "symbol_type": attrs.get("symbol_type", "function"),
                }
            )

        res_edges = []
        count = 0
        for u, v, eattrs in subgraph.edges(data=True):
            if count >= max_edges:
                break
            res_edges.append(
                {
                    "source": u,
                    "target": v,
                    "relationship": "calls",
                    "ambiguous": eattrs.get("ambiguous", False),
                }
            )
            count += 1

        return {
            "nodes": res_nodes,
            "edges": res_edges,
            "node_count": subgraph.number_of_nodes(),
            "edge_count": subgraph.number_of_edges(),
        }
