"""Snapshot-Aware Call Site Index (Phase 10, 16, 17).

Provides O(1) in-memory lookups for caller and callee relationships across
a repository snapshot, keyed authoritatively by (repo_name, commit_sha).

Preserves bounded depth traversal (depth 1 direct, depth 2-3 transitive)
with rich relationship provenance, exact source lines, and confidence tiers.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Any

import networkx as nx

from models.call_graph import CallRelationshipType

logger = logging.getLogger(__name__)


@dataclass
class CallEdgeInfo:
    """Detailed metadata for a single call graph edge."""

    caller_id: str
    callee_id: str
    caller_file: str
    caller_name: str
    callee_file: str
    callee_name: str
    call_line: int
    relationship: str
    receiver_expr: Optional[str]
    receiver_type: Optional[str]
    confidence_tier: str
    ambiguous: bool
    depth: int = 1
    propagation_path: List[str] = field(default_factory=list)


class CallSiteIndex:
    """In-memory index of call-site relationships for a single repository snapshot."""

    __test__ = False  # Prevent pytest collection

    _instances: Dict[str, "CallSiteIndex"] = {}
    _lock = threading.RLock()

    def __init__(self, repo_name: str, snapshot_id: str):
        self.repo_name = repo_name
        self.snapshot_id = snapshot_id
        # target_node_id -> list of incoming CallEdgeInfo
        self.callers_by_target: Dict[str, List[CallEdgeInfo]] = {}
        # caller_node_id -> list of outgoing CallEdgeInfo
        self.callees_by_caller: Dict[str, List[CallEdgeInfo]] = {}
        # target_symbol_name -> set of node_ids
        self.symbol_to_nodes: Dict[str, Set[str]] = {}
        # file_path -> set of node_ids
        self.file_to_nodes: Dict[str, Set[str]] = {}
        self._initialized = False

    @classmethod
    def get_index(cls, repo_name: str) -> "CallSiteIndex":
        snapshot_id = cls._resolve_canonical_snapshot(repo_name)
        with cls._lock:
            existing = cls._instances.get(repo_name)
            if (
                existing
                and existing.snapshot_id == snapshot_id
                and existing._initialized
            ):
                return existing
            index = cls(repo_name, snapshot_id)
            cls._instances[repo_name] = index
            return index

    @classmethod
    def clear_cache(cls) -> None:
        with cls._lock:
            cls._instances.clear()

    @staticmethod
    def _resolve_canonical_snapshot(repo_name: str) -> str:
        safe_name = repo_name.replace("/", "_")
        candidates = [
            os.path.join("data", "cloned_repos", safe_name),
            os.path.join("data", "repos", safe_name),
            repo_name,
        ]
        if repo_name in ("VarshithReddy2006/ARIA", "ARIA"):
            candidates.insert(0, ".")

        for c in candidates:
            if os.path.isdir(c) and os.path.exists(os.path.join(c, ".git")):
                try:
                    out = subprocess.check_output(
                        ["git", "rev-parse", "HEAD"],
                        cwd=c,
                        stderr=subprocess.DEVNULL,
                        text=True,
                    ).strip()
                    if out:
                        return f"{repo_name}@{out}"
                except Exception:
                    pass
        return f"{repo_name}@static"

    def populate_from_graph(self, G: nx.DiGraph) -> None:
        """Populate the in-memory index from a NetworkX DiGraph."""
        with self._lock:
            self.callers_by_target.clear()
            self.callees_by_caller.clear()
            self.symbol_to_nodes.clear()
            self.file_to_nodes.clear()

            for nid, attrs in G.nodes(data=True):
                q = attrs.get("qualified", nid.split("::")[-1])
                name = attrs.get("name", q.split(".")[-1])
                f_path = attrs.get("file_path", nid.split("::")[0])

                self.symbol_to_nodes.setdefault(name, set()).add(nid)
                self.symbol_to_nodes.setdefault(q, set()).add(nid)
                self.file_to_nodes.setdefault(f_path, set()).add(nid)

            for u, v, data in G.edges(data=True):
                u_file, u_qual = u.split("::", 1) if "::" in u else (u, u)
                v_file, v_qual = v.split("::", 1) if "::" in v else (v, v)

                edge_info = CallEdgeInfo(
                    caller_id=u,
                    callee_id=v,
                    caller_file=u_file,
                    caller_name=u_qual,
                    callee_file=v_file,
                    callee_name=v_qual,
                    call_line=data.get("call_line", 0),
                    relationship=data.get(
                        "relationship", CallRelationshipType.DIRECT_CALL.value
                    ),
                    receiver_expr=data.get("receiver_expr"),
                    receiver_type=data.get("receiver_type"),
                    confidence_tier=data.get("confidence_tier", "HIGH"),
                    ambiguous=data.get("ambiguous", False),
                )

                self.callers_by_target.setdefault(v, []).append(edge_info)
                self.callees_by_caller.setdefault(u, []).append(edge_info)

            self._initialized = True

    def find_target_node_ids(
        self, symbols: List[Any], seed_files: List[str]
    ) -> Set[str]:
        """Map changed symbols or files to concrete call graph node IDs."""
        targets: Set[str] = set()

        for sym in symbols:
            s_name = getattr(sym, "name", str(sym))
            s_file = getattr(sym, "file_path", "")
            s_parent = getattr(sym, "parent_class", None)

            q = f"{s_parent}.{s_name}" if s_parent else s_name
            exact_id = f"{s_file}::{q}" if s_file else None

            if (
                exact_id
                and exact_id in self.callers_by_target
                or (exact_id and exact_id in self.callees_by_caller)
            ):
                targets.add(exact_id)
                continue

            # Lookup by qualified name or symbol name
            if q in self.symbol_to_nodes:
                cands = self.symbol_to_nodes[q]
                if s_file:
                    file_matched = {c for c in cands if c.startswith(s_file)}
                    targets.update(file_matched if file_matched else cands)
                else:
                    targets.update(cands)
            elif s_name in self.symbol_to_nodes:
                cands = self.symbol_to_nodes[s_name]
                if s_file:
                    file_matched = {c for c in cands if c.startswith(s_file)}
                    targets.update(file_matched if file_matched else cands)
                else:
                    targets.update(cands)

        # Fallback to seed files if no symbols matched
        if not targets and seed_files:
            for sf in seed_files:
                if sf in self.file_to_nodes:
                    targets.update(self.file_to_nodes[sf])

        return targets

    def resolve_callers(
        self,
        target_nodes: Set[str],
        max_depth: int = 3,
    ) -> Tuple[List[CallEdgeInfo], List[CallEdgeInfo]]:
        """Perform bounded traversal to find direct (depth 1) and transitive (depth 2-3) callers.

        Returns: (direct_callers, transitive_callers)
        """
        direct_callers: List[CallEdgeInfo] = []
        transitive_callers: List[CallEdgeInfo] = []

        visited: Set[str] = set(target_nodes)
        queue: List[Tuple[str, int, List[str]]] = [(t, 0, [t]) for t in target_nodes]

        while queue:
            curr_target, depth, path = queue.pop(0)
            if depth >= max_depth:
                continue

            incoming_edges = self.callers_by_target.get(curr_target, [])
            for edge in incoming_edges:
                caller_node = edge.caller_id
                if caller_node in visited:
                    continue
                visited.add(caller_node)

                new_path = path + [caller_node]
                info = CallEdgeInfo(
                    caller_id=edge.caller_id,
                    callee_id=edge.callee_id,
                    caller_file=edge.caller_file,
                    caller_name=edge.caller_name,
                    callee_file=edge.callee_file,
                    callee_name=edge.callee_name,
                    call_line=edge.call_line,
                    relationship=edge.relationship,
                    receiver_expr=edge.receiver_expr,
                    receiver_type=edge.receiver_type,
                    confidence_tier=edge.confidence_tier if depth == 0 else "MEDIUM",
                    ambiguous=edge.ambiguous,
                    depth=depth + 1,
                    propagation_path=new_path,
                )

                if depth == 0:
                    direct_callers.append(info)
                else:
                    transitive_callers.append(info)

                queue.append((caller_node, depth + 1, new_path))

        return direct_callers, transitive_callers
