"""Impact Analysis & Dependency Path Explorer.

Computes change blast radius across APIs, services, and tests, and traces shortest dependency paths between nodes.
"""

from __future__ import annotations

from collections import deque
from typing import Dict, List, Set, Any
from .layer_classifier import classify_layer


def compute_blast_radius(
    node_id: str, graph_edges: List[Dict[str, str]]
) -> Dict[str, Any]:
    """Compute change blast radius for a given target node."""
    incoming_adj: Dict[str, List[str]] = {}
    for edge in graph_edges:
        src = edge.get("source") or edge.get("src")
        tgt = edge.get("target") or edge.get("dst")
        if src and tgt:
            incoming_adj.setdefault(tgt, []).append(src)

    direct_consumers = incoming_adj.get(node_id, [])
    visited: Set[str] = set(direct_consumers)
    queue = deque(direct_consumers)

    while queue:
        curr = queue.popleft()
        for parent in incoming_adj.get(curr, []):
            if parent not in visited:
                visited.add(parent)
                queue.append(parent)

    all_affected = list(visited)
    affected_apis = [f for f in all_affected if "api" in f.lower() or "router" in f.lower()]
    affected_services = [f for f in all_affected if "service" in f.lower()]
    affected_tests = [f for f in all_affected if "test" in f.lower() or "spec" in f.lower()]
    affected_entry_points = [f for f in all_affected if classify_layer(f) == "Presentation"]

    total_affected = len(all_affected)
    risk_level = "Low"
    if total_affected > 15 or len(affected_apis) > 3:
        risk_level = "Critical"
    elif total_affected > 8:
        risk_level = "High"
    elif total_affected > 3:
        risk_level = "Medium"

    return {
        "node_id": node_id,
        "direct_consumers": direct_consumers,
        "indirect_consumers": [f for f in all_affected if f not in direct_consumers],
        "total_affected_files": total_affected,
        "affected_entry_points": affected_entry_points,
        "affected_apis": affected_apis,
        "affected_services": affected_services,
        "affected_tests": affected_tests,
        "risk_level": risk_level,
        "estimated_blast_radius_pct": min(100, total_affected * 5),
    }


def find_shortest_path(
    source_id: str, target_id: str, graph_edges: List[Dict[str, str]]
) -> Dict[str, Any]:
    """Find shortest dependency path between source_id and target_id using BFS."""
    if source_id == target_id:
        return {
            "source": source_id,
            "target": target_id,
            "distance": 0,
            "path_nodes": [source_id],
            "cross_layer_transitions": 0,
            "has_cycle": False,
        }

    adj: Dict[str, List[str]] = {}
    for edge in graph_edges:
        src = edge.get("source") or edge.get("src")
        tgt = edge.get("target") or edge.get("dst")
        if src and tgt:
            adj.setdefault(src, []).append(tgt)

    queue = deque([[source_id]])
    visited = {source_id}

    while queue:
        path = queue.popleft()
        curr = path[-1]

        if curr == target_id:
            transitions = 0
            for i in range(len(path) - 1):
                if classify_layer(path[i]) != classify_layer(path[i + 1]):
                    transitions += 1

            return {
                "source": source_id,
                "target": target_id,
                "distance": len(path) - 1,
                "path_nodes": path,
                "cross_layer_transitions": transitions,
                "has_cycle": False,
            }

        for nxt in adj.get(curr, []):
            if nxt not in visited:
                visited.add(nxt)
                queue.append(path + [nxt])

    return {
        "source": source_id,
        "target": target_id,
        "distance": -1,
        "path_nodes": [],
        "cross_layer_transitions": 0,
        "has_cycle": False,
    }
