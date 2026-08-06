"""Tarjan SCC Cycle Detector.

Detects strongly connected component (SCC) dependency cycles in python/typescript module graphs.
Identifies module cycles, package cycles, and layer cycles with breakpoint recommendations.
"""

from __future__ import annotations

import os
from typing import Dict, List, Set, Any


def detect_cycles(graph_edges: List[Dict[str, str]]) -> Dict[str, Any]:
    """Detect cyclic dependencies using Tarjan's Strongly Connected Components algorithm."""
    nodes: Set[str] = set()
    adj: Dict[str, List[str]] = {}

    for edge in graph_edges:
        src = edge.get("source") or edge.get("src")
        tgt = edge.get("target") or edge.get("dst")
        if src and tgt and src != tgt:
            nodes.add(src)
            nodes.add(tgt)
            adj.setdefault(src, []).append(tgt)
            adj.setdefault(tgt, [])

    index = 0
    stack: List[str] = []
    indices: Dict[str, int] = {}
    lowlink: Dict[str, int] = {}
    on_stack: Set[str] = set()
    sccs: List[List[str]] = []

    def strongconnect(node: str):
        nonlocal index
        indices[node] = index
        lowlink[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)

        for neighbor in adj.get(node, []):
            if neighbor not in indices:
                strongconnect(neighbor)
                lowlink[node] = min(lowlink[node], lowlink[neighbor])
            elif neighbor in on_stack:
                lowlink[node] = min(lowlink[node], indices[neighbor])

        if lowlink[node] == indices[node]:
            scc = []
            while True:
                w = stack.pop()
                on_stack.remove(w)
                scc.append(w)
                if w == node:
                    break
            if len(scc) > 1:
                sccs.append(scc)

    for node in nodes:
        if node not in indices:
            strongconnect(node)

    cycle_groups = []
    breakpoint_suggestions = []

    for idx, scc in enumerate(sccs, 1):
        cycle_groups.append(
            {
                "cycle_id": f"cycle-{idx}",
                "nodes": scc,
                "size": len(scc),
            }
        )

        # Suggest breaking feedback edge
        src_mod = scc[0]
        tgt_mod = scc[1] if len(scc) > 1 else scc[0]
        breakpoint_suggestions.append(
            {
                "cycle_id": f"cycle-{idx}",
                "break_edge": f"{src_mod} -> {tgt_mod}",
                "reason": "Circular import chain detected.",
                "suggestion": f"Introduce an Interface or Event Publisher between '{os.path.basename(src_mod)}' and '{os.path.basename(tgt_mod)}'.",
            }
        )

    return {
        "cycle_count": len(cycle_groups),
        "cycle_groups": cycle_groups,
        "breakpoint_suggestions": breakpoint_suggestions,
    }
