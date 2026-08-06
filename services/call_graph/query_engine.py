"""Call Graph Query Engine Component.

Responsible for executing graph algorithms, traversals (BFS), caller/callee lookups,
call hierarchy trees, blast radius calculation, graph statistics, and unreachable functions.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

import networkx as nx

from models.call_graph import (
    BlastRadiusResult,
    CallHierarchyNode,
    CallNode,
)
from services.call_graph.store import CallGraphStore

logger = logging.getLogger(__name__)

# Risk thresholds for blast radius
_BLAST_HIGH = 20
_BLAST_MED = 5

# Max BFS depth for hierarchy / blast radius
_MAX_HIERARCHY_DEPTH = 8
_MAX_BLAST_DEPTH = 10


class CallGraphQueryEngine:
    """Executes query algorithms and graph traversals on loaded NetworkX call graphs."""

    def __init__(self, store: CallGraphStore) -> None:
        self.store = store

    def get_node(self, repo_name: str, function_id: str) -> Optional[CallNode]:
        """Return metadata for a single function node."""
        G = self.store.load_graph(repo_name)
        if G is None or function_id not in G:
            return None
        return self.node_from_graph(G, function_id)

    def get_callers(self, repo_name: str, function_id: str) -> List[CallNode]:
        """Return all functions that directly call *function_id*."""
        G = self.store.load_graph(repo_name)
        if G is None or function_id not in G:
            return []
        return [self.node_from_graph(G, n) for n in G.predecessors(function_id)]

    def get_callees(self, repo_name: str, function_id: str) -> List[CallNode]:
        """Return all functions directly called by *function_id*."""
        G = self.store.load_graph(repo_name)
        if G is None or function_id not in G:
            return []
        return [self.node_from_graph(G, n) for n in G.successors(function_id)]

    def get_blast_radius(self, repo_name: str, function_id: str) -> BlastRadiusResult:
        """Compute function-level blast radius via BFS on callers.

        'Who would be affected if I changed this function?' — walks backward
        through the call graph to find all functions that transitively call
        function_id, up to _MAX_BLAST_DEPTH hops.
        """
        G = self.store.load_graph(repo_name)
        if G is None or function_id not in G:
            return BlastRadiusResult(
                function_id=function_id,
                risk_level="low",
            )

        # BFS on reversed graph (callers of callers)
        affected: Set[str] = set()
        queue = [(function_id, 0)]
        max_depth_reached = 0

        while queue:
            node, depth = queue.pop(0)
            if depth >= _MAX_BLAST_DEPTH:
                continue
            for caller in G.predecessors(node):
                if caller not in affected and caller != function_id:
                    affected.add(caller)
                    max_depth_reached = max(max_depth_reached, depth + 1)
                    queue.append((caller, depth + 1))

        affected_list = sorted(affected)
        affected_files = sorted(
            {
                G.nodes[n].get("file_path", "")
                for n in affected_list
                if G.nodes[n].get("file_path")
            }
        )

        n = len(affected_list)
        risk = "high" if n >= _BLAST_HIGH else "medium" if n >= _BLAST_MED else "low"

        # Detect SCCs (mutual recursion / cycles) in the affected subgraph
        subgraph = G.subgraph(set(affected_list) | {function_id})
        sccs = [
            list(c) for c in nx.strongly_connected_components(subgraph) if len(c) > 1
        ]

        return BlastRadiusResult(
            function_id=function_id,
            affected_functions=affected_list,
            affected_files=affected_files,
            depth=max_depth_reached,
            risk_level=risk,
            recursive_cycles=sccs,
        )

    def get_hierarchy(
        self,
        repo_name: str,
        function_id: str,
        direction: str = "down",
        max_depth: int = _MAX_HIERARCHY_DEPTH,
    ) -> Optional[CallHierarchyNode]:
        """Build a call hierarchy tree rooted at *function_id*.

        direction="down": show what this function calls (callees).
        direction="up":   show what calls this function (callers).
        """
        G = self.store.load_graph(repo_name)
        if G is None or function_id not in G:
            return None

        visited: Set[str] = set()

        def build_tree(node_id: str, depth: int) -> CallHierarchyNode:
            attrs = G.nodes.get(node_id, {})
            is_back_edge = node_id in visited and depth > 0
            visited.add(node_id)

            children: List[CallHierarchyNode] = []
            if depth < max_depth and not is_back_edge:
                neighbours = (
                    list(G.successors(node_id))
                    if direction == "down"
                    else list(G.predecessors(node_id))
                )
                for nb in neighbours:
                    children.append(build_tree(nb, depth + 1))

            return CallHierarchyNode(
                node_id=node_id,
                name=attrs.get("name", node_id),
                qualified=attrs.get("qualified", node_id),
                file_path=attrs.get("file_path", ""),
                children=children,
                depth=depth,
                is_recursive_back_edge=is_back_edge,
            )

        return build_tree(function_id, 0)

    def get_stats(self, repo_name: str) -> Dict[str, Any]:
        """Return aggregate call graph statistics."""
        G = self.store.load_graph(repo_name)
        summary = self.store.load_summary(repo_name)

        if G is None:
            return {"error": "Call graph not found. Run build first."}

        sccs = list(nx.strongly_connected_components(G))
        non_trivial_sccs = [c for c in sccs if len(c) > 1]

        return {
            "node_count": G.number_of_nodes(),
            "edge_count": G.number_of_edges(),
            "entry_functions": len([n for n in G.nodes() if G.in_degree(n) == 0]),
            "recursive_functions": len([n for n in G.nodes() if G.has_edge(n, n)]),
            "mutual_recursion_groups": len(non_trivial_sccs),
            "top_fan_in": summary.top_fan_in if summary else [],
            "top_fan_out": summary.top_fan_out if summary else [],
            "generated_at": summary.generated_at if summary else None,
        }

    def get_unreachable_functions(
        self, repo_name: str, entry_function_ids: Optional[List[str]] = None
    ) -> List[str]:
        """Return function IDs unreachable from entry points.

        Used by Dead Code Detection to surface unreachable functions
        (not just unreachable files).
        """
        G = self.store.load_graph(repo_name)
        if G is None:
            return []

        # Use provided entry points or auto-detect (nodes with no callers)
        entries = set(entry_function_ids or [])
        if not entries:
            entries = {n for n in G.nodes() if G.in_degree(n) == 0}

        reachable: Set[str] = set(entries)
        for ep in entries:
            if ep in G:
                reachable.update(nx.descendants(G, ep))

        return sorted(set(G.nodes()) - reachable)

    def search_functions(
        self, repo_name: str, query: str, limit: int = 20
    ) -> List[CallNode]:
        """Search for functions by name substring."""
        G = self.store.load_graph(repo_name)
        if G is None:
            return []
        q = query.lower()
        matches = []
        for nid in G.nodes():
            attrs = G.nodes[nid]
            name = attrs.get("name", "").lower()
            qualified = attrs.get("qualified", "").lower()
            if q in name or q in qualified or q in nid.lower():
                matches.append(self.node_from_graph(G, nid))
        return matches[:limit]

    @staticmethod
    def bfs(
        G: nx.DiGraph,
        start: str,
        forward: bool,
        max_depth: int,
    ) -> Set[str]:
        """Simple BFS returning visited nodes (excluding start)."""
        if start not in G:
            return set()
        visited: Set[str] = set()
        queue = [(start, 0)]
        while queue:
            node, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            neighbours = (
                list(G.successors(node)) if forward else list(G.predecessors(node))
            )
            for nb in neighbours:
                if nb not in visited and nb != start:
                    visited.add(nb)
                    queue.append((nb, depth + 1))
        return visited

    @staticmethod
    def node_from_graph(G: nx.DiGraph, node_id: str) -> CallNode:
        attrs = G.nodes.get(node_id, {})
        return CallNode(
            node_id=node_id,
            name=attrs.get("name", node_id),
            qualified=attrs.get("qualified", node_id),
            file_path=attrs.get("file_path", ""),
            line_number=attrs.get("line_number", 1),
            language=attrs.get("language", "unknown"),
            symbol_type=attrs.get("symbol_type", "function"),
            parent_class=attrs.get("parent_class") or None,
            is_entry=attrs.get("is_entry", False),
            is_recursive=attrs.get("is_recursive", False),
            fan_in=G.in_degree(node_id),
            fan_out=G.out_degree(node_id),
        )
