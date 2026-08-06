"""Function Call Graph Service Facade.

Builds a function-to-function directed graph from a repository's Tree-sitter
AST and Symbol Index, then exposes algorithms for callers, callees, blast
radius, hierarchy, SCCs, and fan-in/fan-out analysis.

This service delegates responsibility to cohesive specialized components:
  - CallGraphExtractor: Tree-sitter AST call site parsing & scope mapping
  - CallGraphStore: Snapshot store & disk persistence management
  - CallGraphBuilder: NetworkX DiGraph full and partial build pipelines
  - CallGraphQueryEngine: Graph traversals, BFS, hierarchy, blast radius, stats
  - CallGraphSerializer: REST API & React Flow JSON representations

Design principles:
  - Reuses SymbolService for definition lookup (no re-parsing definitions).
  - Reuses TreeSitterService._get_parser() for call-site extraction.
  - Reuses GraphService.save_graph() / load_graph() for persistence.
  - Node IDs: "{file_path}::{qualified_name}"  (no collisions across files).
  - Disambiguation: same-file > same-dir > global; ties marked ambiguous=True.
  - Fabricated edges are never emitted. Prefer missing over incorrect.
  - Zero LLM calls. All computation is deterministic.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Generator, List, Optional, Set, Tuple

import networkx as nx

from core.cache import AnalysisCache
from core.repository_context import RepositoryContext
from models.call_graph import (
    BlastRadiusResult,
    CallGraphSummary,
    CallHierarchyNode,
    CallNode,
)
from models.symbol import Symbol
from services.call_graph.builder import CallGraphBuilder
from services.call_graph.extractor import (
    CallGraphExtractor,
    _file_dir,
    _node_id,
    _qualified,
)
from services.call_graph.query_engine import (
    _BLAST_HIGH,
    _BLAST_MED,
    _MAX_BLAST_DEPTH,
    _MAX_HIERARCHY_DEPTH,
    CallGraphQueryEngine,
)
from services.call_graph.serializer import CallGraphSerializer
from services.call_graph.store import _CALL_GRAPHS_DIR, _SCHEMA_VERSION, CallGraphStore
from services.graph_service import GraphService
from services.symbol_service import SymbolService
from storage.snapshot_store import SnapshotStore

logger = logging.getLogger(__name__)

# Re-export module-level constants and helper functions for backward compatibility
__all__ = [
    "CallGraphService",
    "_CALL_GRAPHS_DIR",
    "_SCHEMA_VERSION",
    "_BLAST_HIGH",
    "_BLAST_MED",
    "_MAX_HIERARCHY_DEPTH",
    "_MAX_BLAST_DEPTH",
    "_node_id",
    "_qualified",
    "_file_dir",
]


class CallGraphService:
    """Builds and queries the function-level call graph.

    Injected as a singleton into the FastAPI app alongside the existing
    service singletons (graph_service, symbol_service, etc.).
    Act as an orchestrating facade delegating to modular call_graph sub-components.
    """

    @property
    def schema_version(self) -> int:
        return _SCHEMA_VERSION

    @classmethod
    def get_schema_version(cls) -> int:
        return _SCHEMA_VERSION

    def __init__(
        self,
        symbol_service: Optional[SymbolService] = None,
        graph_service: Optional[GraphService] = None,
        call_graphs_dir: str = _CALL_GRAPHS_DIR,
        snapshot_store: Optional[SnapshotStore] = None,
        analysis_cache: Optional[AnalysisCache] = None,
    ) -> None:
        self.symbol_service = symbol_service or SymbolService()
        self.graph_service = graph_service or GraphService()
        self.call_graphs_dir = call_graphs_dir

        self.store = CallGraphStore(
            graph_service=self.graph_service,
            call_graphs_dir=call_graphs_dir,
            snapshot_store=snapshot_store,
            analysis_cache=analysis_cache,
        )
        self.snapshot_store = self.store.snapshot_store
        self.analysis_cache = self.store.analysis_cache

        self.extractor = CallGraphExtractor()
        self._ts = self.extractor._ts

        self.builder = CallGraphBuilder(
            extractor=self.extractor,
            store=self.store,
            symbol_service=self.symbol_service,
        )

        self.query_engine = CallGraphQueryEngine(store=self.store)
        self.serializer = CallGraphSerializer(
            store=self.store, query_engine=self.query_engine
        )

    # ------------------------------------------------------------------
    # Public build API
    # ------------------------------------------------------------------

    def build(
        self,
        repo_name: str,
        files: Optional[List[Dict[str, str]]] = None,
        context: Optional[RepositoryContext] = None,
    ) -> Generator[Dict[str, Any], None, CallGraphSummary]:
        """Build the call graph. Yields SSE-style progress events.

        Provides backward compatibility by delegating to build_full.
        """
        return (yield from self.build_full(repo_name, context=context, files=files))

    def build_full(
        self,
        repo_name: str,
        context: Optional[RepositoryContext] = None,
        files: Optional[List[Dict[str, str]]] = None,
    ) -> Generator[Dict[str, Any], None, CallGraphSummary]:
        """Build the call graph from scratch."""
        return (yield from self.builder.build_full(repo_name, context, files))

    def build_partial(
        self,
        repo_name: str,
        changed_files: Set[str],
        context: Optional[RepositoryContext] = None,
        files: Optional[List[Dict[str, str]]] = None,
    ) -> Generator[Dict[str, Any], None, CallGraphSummary]:
        """Incrementally update call edges and rebuild the call graph."""
        return (
            yield from self.builder.build_partial(
                repo_name, changed_files, context, files
            )
        )

    # ------------------------------------------------------------------
    # Public query API
    # ------------------------------------------------------------------

    def graph_exists(self, repo_name: str) -> bool:
        """Return True if a call graph persistence file exists."""
        return self.store.graph_exists(repo_name)

    def load_graph(self, repo_name: str) -> Optional[nx.DiGraph]:
        """Load the call graph from disk."""
        return self.store.load_graph(repo_name)

    def load_summary(self, repo_name: str) -> Optional[CallGraphSummary]:
        """Load the persisted call graph summary."""
        return self.store.load_summary(repo_name)

    def get_node(self, repo_name: str, function_id: str) -> Optional[CallNode]:
        """Return metadata for a single function node."""
        return self.query_engine.get_node(repo_name, function_id)

    def get_callers(self, repo_name: str, function_id: str) -> List[CallNode]:
        """Return all functions that directly call *function_id*."""
        return self.query_engine.get_callers(repo_name, function_id)

    def get_callees(self, repo_name: str, function_id: str) -> List[CallNode]:
        """Return all functions directly called by *function_id*."""
        return self.query_engine.get_callees(repo_name, function_id)

    def get_blast_radius(self, repo_name: str, function_id: str) -> BlastRadiusResult:
        """Compute function-level blast radius via BFS on callers."""
        return self.query_engine.get_blast_radius(repo_name, function_id)

    def get_hierarchy(
        self,
        repo_name: str,
        function_id: str,
        direction: str = "down",
        max_depth: int = _MAX_HIERARCHY_DEPTH,
    ) -> Optional[CallHierarchyNode]:
        """Build a call hierarchy tree rooted at *function_id*."""
        return self.query_engine.get_hierarchy(
            repo_name, function_id, direction, max_depth
        )

    def get_stats(self, repo_name: str) -> Dict[str, Any]:
        """Return aggregate call graph statistics."""
        return self.query_engine.get_stats(repo_name)

    def get_unreachable_functions(
        self, repo_name: str, entry_function_ids: Optional[List[str]] = None
    ) -> List[str]:
        """Return function IDs unreachable from entry points."""
        return self.query_engine.get_unreachable_functions(
            repo_name, entry_function_ids
        )

    def search_functions(
        self, repo_name: str, query: str, limit: int = 20
    ) -> List[CallNode]:
        """Search for functions by name substring."""
        return self.query_engine.search_functions(repo_name, query, limit)

    # ------------------------------------------------------------------
    # React Flow serialisation
    # ------------------------------------------------------------------

    def get_graph_json(
        self,
        repo_name: str,
        search_query: Optional[str] = None,
        max_nodes: int = 300,
        max_edges: int = 1000,
    ) -> Dict[str, Any]:
        """Return the call graph as React Flow-compatible JSON."""
        return self.serializer.get_graph_json(
            repo_name, search_query, max_nodes, max_edges
        )

    def get_neighbors_json(self, repo_name: str, function_id: str) -> Dict[str, Any]:
        """Return immediate callers + callees as React Flow JSON."""
        return self.serializer.get_neighbors_json(repo_name, function_id)

    def get_trace_json(
        self,
        repo_name: str,
        function_id: str,
        direction: str = "both",
        depth: int = 6,
    ) -> Dict[str, Any]:
        """Return BFS trace from *function_id* as React Flow JSON."""
        return self.serializer.get_trace_json(repo_name, function_id, direction, depth)

    # ------------------------------------------------------------------
    # Backward-compatible internal / static methods
    # ------------------------------------------------------------------

    def _extract_call_edges(
        self,
        file_path: str,
        content: str,
        defn_by_name: Dict[str, List[Symbol]],
        all_nodes: Dict[str, CallNode],
    ) -> List[Tuple[str, str, int, bool]]:
        return self.extractor.extract_call_edges(
            file_path, content, defn_by_name, all_nodes
        )

    def _build_scope_map(
        self,
        root,
        file_path: str,
        all_nodes: Dict[str, CallNode],
        language_name: str,
    ) -> List[Tuple[int, int, str]]:
        return self.extractor.build_scope_map(
            root, file_path, all_nodes, language_name
        )

    def _find_call_sites(self, root, language_name: str) -> List[Tuple[str, int, int]]:
        return self.extractor.find_call_sites(root, language_name)

    @staticmethod
    def _find_enclosing_scope(
        call_byte: int,
        scopes: List[Tuple[int, int, str]],
    ) -> Optional[str]:
        return CallGraphExtractor.find_enclosing_scope(call_byte, scopes)

    def _resolve_callee(
        self,
        call_name: str,
        caller_id: str,
        caller_file: str,
        defn_by_name: Dict[str, List[Symbol]],
        all_nodes: Dict[str, CallNode],
    ) -> Tuple[Optional[str], bool]:
        return self.extractor.resolve_callee(
            call_name, caller_id, caller_file, defn_by_name, all_nodes
        )

    def _serialise_subgraph(
        self,
        G: nx.DiGraph,
        node_ids: Set[str],
        focus_id: Optional[str] = None,
        highlighted: Optional[Set[str]] = None,
        max_edges: int = 1000,
    ) -> Dict[str, Any]:
        return self.serializer.serialise_subgraph(
            G, node_ids, focus_id, highlighted, max_edges
        )

    @staticmethod
    def _get_first_identifier(node) -> str:
        return CallGraphExtractor.get_first_identifier(node)

    @staticmethod
    def _bfs(
        G: nx.DiGraph,
        start: str,
        forward: bool,
        max_depth: int,
    ) -> Set[str]:
        return CallGraphQueryEngine.bfs(G, start, forward, max_depth)

    @staticmethod
    def _node_from_graph(G: nx.DiGraph, node_id: str) -> CallNode:
        return CallGraphQueryEngine.node_from_graph(G, node_id)

    def _summary_path(self, repo_name: str) -> str:
        return self.store.summary_path(repo_name)

    def _save_summary(self, repo_name: str, summary: CallGraphSummary) -> None:
        self.store.save_summary(repo_name, summary)

    def _load_raw_summary(self, repo_name: str) -> Optional[Dict[str, Any]]:
        return self.store._load_raw_summary(repo_name)
