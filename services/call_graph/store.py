"""Call Graph Storage Component.

Responsible for graph persistence, disk summary reading/writing,
and interacting with GraphService, SnapshotStore, and AnalysisCache.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

import networkx as nx

from core.cache import AnalysisCache
from models.call_graph import CallGraphSummary
from services.graph_service import GraphService
from storage.snapshot_store import SnapshotStore

logger = logging.getLogger(__name__)

_CALL_GRAPHS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "call_graphs",
)
_SCHEMA_VERSION = 1


class CallGraphStore:
    """Manages disk persistence and caching for call graph models and summaries."""

    def __init__(
        self,
        graph_service: Optional[GraphService] = None,
        call_graphs_dir: str = _CALL_GRAPHS_DIR,
        snapshot_store: Optional[SnapshotStore] = None,
        analysis_cache: Optional[AnalysisCache] = None,
    ) -> None:
        self.graph_service = graph_service or GraphService()
        self.call_graphs_dir = call_graphs_dir
        os.makedirs(self.call_graphs_dir, exist_ok=True)

        if snapshot_store is None:
            if call_graphs_dir != _CALL_GRAPHS_DIR:
                parent_dir = os.path.dirname(call_graphs_dir)
                dir_name = os.path.basename(call_graphs_dir)
                from storage.snapshot_store import JsonSnapshotStore

                self.snapshot_store = JsonSnapshotStore(
                    base_dir=parent_dir, key_map={"call_graphs": dir_name}
                )
            else:
                from storage.snapshot_store import JsonSnapshotStore

                self.snapshot_store = JsonSnapshotStore()
        else:
            self.snapshot_store = snapshot_store

        self.analysis_cache = analysis_cache or AnalysisCache()

    def graph_exists(self, repo_name: str) -> bool:
        """Return True if a call graph persistence file exists."""
        return self.graph_service.graph_exists(f"{repo_name}_call_graph")

    def load_graph(self, repo_name: str) -> Optional[nx.DiGraph]:
        """Load the call graph from disk or in-memory cache."""
        cached = self.analysis_cache.get(repo_name, "graphs", 1, subkey="call")
        if cached is not None:
            return cached

        graph = self.graph_service.load_graph(f"{repo_name}_call_graph")
        if graph is not None:
            self.analysis_cache.set(repo_name, "graphs", graph, 1, subkey="call")
        return graph

    def save_graph(self, repo_name: str, G: nx.DiGraph) -> None:
        """Save graph to disk and update analysis cache."""
        self.graph_service.save_graph(G, f"{repo_name}_call_graph")
        self.analysis_cache.set(repo_name, "graphs", G, 1, subkey="call")

    def load_summary(self, repo_name: str) -> Optional[CallGraphSummary]:
        """Load the persisted call graph summary."""
        cached = self.analysis_cache.get(repo_name, "call_graph", _SCHEMA_VERSION)
        if cached is not None:
            return cached

        data = self._load_raw_summary(repo_name)
        if data is None:
            return None

        stored_ver = data.get("_schema_version", 0)
        if stored_ver < _SCHEMA_VERSION:
            logger.warning(
                "Discarding stale call graph summary for %s (v%d < v%d)",
                repo_name,
                stored_ver,
                _SCHEMA_VERSION,
            )
            return None

        try:
            filtered = {k: v for k, v in data.items() if not k.startswith("_")}
            summary = CallGraphSummary(**filtered)
            self.analysis_cache.set(repo_name, "call_graph", summary, _SCHEMA_VERSION)
            return summary
        except Exception as exc:
            logger.error("Failed to deserialise call graph summary: %s", exc)
            return None

    def save_summary(self, repo_name: str, summary: CallGraphSummary) -> None:
        """Save call graph summary to snapshot store and cache."""
        payload = summary.model_dump()
        payload["_schema_version"] = _SCHEMA_VERSION
        payload["_built_at"] = int(time.time())
        self.snapshot_store.save(repo_name, "call_graphs", payload)
        self.analysis_cache.set(repo_name, "call_graph", summary, _SCHEMA_VERSION)

    def summary_path(self, repo_name: str) -> str:
        """Return path to stored call graph summary file."""
        return self.snapshot_store._get_path(repo_name, "call_graphs")

    def save_call_edges_cache(
        self, repo_name: str, file_edges_map: Dict[str, Any]
    ) -> None:
        """Save call edges map to snapshot store."""
        self.snapshot_store.save(
            repo_name, "call_edges", {"edges": file_edges_map, "_schema_version": 1}
        )

    def load_call_edges_cache(self, repo_name: str) -> Optional[Dict[str, Any]]:
        """Load call edges map from snapshot store."""
        return self.snapshot_store.load(repo_name, "call_edges")

    def _load_raw_summary(self, repo_name: str) -> Optional[Dict[str, Any]]:
        return self.snapshot_store.load(repo_name, "call_graphs")
