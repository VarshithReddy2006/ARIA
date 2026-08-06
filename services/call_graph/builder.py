"""Call Graph Builder Component.

Responsible for executing full and partial (incremental) call graph construction
jobs, computing node metrics, and assembling NetworkX DiGraph instances.
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Optional, Set

import networkx as nx

from core.repository_context import RepositoryContext
from models.call_graph import CallGraphSummary, CallNode
from models.symbol import Symbol
from services.call_graph.extractor import CallGraphExtractor, _node_id, _qualified
from services.call_graph.store import CallGraphStore
from services.symbol_service import SymbolService

logger = logging.getLogger(__name__)


class CallGraphBuilder:
    """Builds and incrementally updates the NetworkX function call graph."""

    def __init__(
        self,
        extractor: CallGraphExtractor,
        store: CallGraphStore,
        symbol_service: Optional[SymbolService] = None,
    ) -> None:
        self.extractor = extractor
        self.store = store
        self.symbol_service = symbol_service or SymbolService()

    def build_full(
        self,
        repo_name: str,
        context: Optional[RepositoryContext] = None,
        files: Optional[List[Dict[str, str]]] = None,
    ) -> Generator[Dict[str, Any], None, CallGraphSummary]:
        """Build the call graph from scratch."""
        yield {"status": "loading_symbols", "message": "Loading symbol index…"}

        if context is not None:
            symbol_index = context.symbol_index
        else:
            symbol_index = self.symbol_service.load(repo_name)

        if symbol_index is None:
            raise ValueError(
                f"No symbol index found for '{repo_name}'. "
                "Run POST /api/architecture/build first."
            )

        if files is None:
            if context and context.repo_path:
                files = self.symbol_service._walk_repo(context.repo_path)
            else:
                files = []

        yield {
            "status": "building_lookup",
            "message": "Building definition lookup table…",
        }

        # Build: name → list[Symbol] for fast callee resolution
        defn_by_name: Dict[str, List[Symbol]] = defaultdict(list)
        for sym in symbol_index.symbols:
            if sym.type in ("function", "method", "class"):
                defn_by_name[sym.name].append(sym)

        yield {
            "status": "extracting_calls",
            "message": f"Extracting call sites from {len(files)} files…",
        }

        # Collect all call edges across the repo
        all_nodes: Dict[str, CallNode] = {}

        # Register all known symbols as nodes first
        for sym in symbol_index.symbols:
            if sym.type in ("function", "method"):
                q = _qualified(sym)
                nid = _node_id(sym.file_path, q)
                if nid not in all_nodes:
                    all_nodes[nid] = CallNode(
                        node_id=nid,
                        name=sym.name,
                        qualified=q,
                        file_path=sym.file_path,
                        line_number=sym.line_number,
                        language=sym.language,
                        symbol_type=sym.type,
                        parent_class=sym.parent_class,
                    )

        # Extract call sites per file
        file_edges_map = {}
        for f in files:
            path = f.get("path", "")
            content = f.get("content", "")
            if not path or not content:
                continue
            file_edges = self.extractor.extract_call_edges(
                path, content, defn_by_name, all_nodes
            )
            file_edges_map[path] = file_edges

        # Cache call edges map
        self.store.save_call_edges_cache(repo_name, file_edges_map)

        # Combine edges
        all_edges = []
        for edges in file_edges_map.values():
            all_edges.extend(edges)

        yield {
            "status": "building_graph",
            "message": f"Building graph ({len(all_nodes)} nodes, {len(all_edges)} edges)…",
        }

        # Build NetworkX DiGraph
        G: nx.DiGraph = nx.DiGraph()

        for nid, node in all_nodes.items():
            G.add_node(
                nid,
                name=node.name,
                qualified=node.qualified,
                file_path=node.file_path,
                line_number=node.line_number,
                language=node.language,
                symbol_type=node.symbol_type,
                parent_class=node.parent_class or "",
            )

        for caller_id, callee_id, call_line, ambiguous in all_edges:
            if caller_id in G and callee_id in G:
                # If edge exists, keep lowest call_line
                if G.has_edge(caller_id, callee_id):
                    existing = G[caller_id][callee_id]
                    if call_line < existing.get("call_line", call_line):
                        G[caller_id][callee_id]["call_line"] = call_line
                else:
                    G.add_edge(
                        caller_id,
                        callee_id,
                        call_line=call_line,
                        ambiguous=ambiguous,
                        relationship="calls",
                    )

        yield {"status": "computing_metrics", "message": "Computing graph metrics…"}

        # Annotate nodes with fan-in / fan-out / recursion
        recursive_ids: List[str] = []
        entry_ids: List[str] = []

        for nid in list(G.nodes()):
            fi = G.in_degree(nid)
            fo = G.out_degree(nid)
            is_recursive = G.has_edge(nid, nid)
            is_entry = fi == 0

            G.nodes[nid]["fan_in"] = fi
            G.nodes[nid]["fan_out"] = fo
            G.nodes[nid]["is_recursive"] = is_recursive
            G.nodes[nid]["is_entry"] = is_entry

            if is_recursive:
                recursive_ids.append(nid)
            if is_entry:
                entry_ids.append(nid)

        yield {"status": "persisting", "message": "Saving call graph…"}

        # Save graph via store
        self.store.save_graph(repo_name, G)

        # Build and save summary
        top_fan_in = sorted(
            [{"node_id": n, "fan_in": G.in_degree(n)} for n in G.nodes()],
            key=lambda x: x["fan_in"],
            reverse=True,
        )[:10]
        top_fan_out = sorted(
            [{"node_id": n, "fan_out": G.out_degree(n)} for n in G.nodes()],
            key=lambda x: x["fan_out"],
            reverse=True,
        )[:10]

        summary = CallGraphSummary(
            repo=repo_name,
            generated_at=datetime.now(timezone.utc).isoformat(),
            node_count=G.number_of_nodes(),
            edge_count=G.number_of_edges(),
            entry_functions=entry_ids[:50],
            recursive_functions=recursive_ids,
            top_fan_in=top_fan_in,
            top_fan_out=top_fan_out,
        )
        self.store.save_summary(repo_name, summary)

        yield {
            "status": "complete",
            "message": f"✓ Call graph built: {G.number_of_nodes()} functions, {G.number_of_edges()} calls",
        }

        return summary

    def build_partial(
        self,
        repo_name: str,
        changed_files: Set[str],
        context: Optional[RepositoryContext] = None,
        files: Optional[List[Dict[str, str]]] = None,
    ) -> Generator[Dict[str, Any], None, CallGraphSummary]:
        """Incrementally update call edges and rebuild the call graph."""
        old_edges_data = self.store.load_call_edges_cache(repo_name)
        if old_edges_data is None:
            logger.info(
                "No existing call edges cache found for %s, running full build.",
                repo_name,
            )
            return (yield from self.build_full(repo_name, context=context, files=files))

        yield {"status": "loading_symbols", "message": "Loading symbol index…"}

        if context is not None:
            symbol_index = context.symbol_index
        else:
            symbol_index = self.symbol_service.load(repo_name)

        if symbol_index is None:
            raise ValueError(
                f"No symbol index found for '{repo_name}'. "
                "Run POST /api/architecture/build first."
            )

        if files is None:
            if context and context.repo_path:
                files = self.symbol_service._walk_repo(context.repo_path)
            else:
                files = []

        yield {
            "status": "building_lookup",
            "message": "Building definition lookup table…",
        }

        # Build: name → list[Symbol] for fast callee resolution
        defn_by_name: Dict[str, List[Symbol]] = defaultdict(list)
        for sym in symbol_index.symbols:
            if sym.type in ("function", "method", "class"):
                defn_by_name[sym.name].append(sym)

        yield {
            "status": "extracting_calls",
            "message": "Extracting call sites from changed files…",
        }

        # Collect all call edges across the repo
        all_nodes: Dict[str, CallNode] = {}

        # Register all known symbols as nodes first
        for sym in symbol_index.symbols:
            if sym.type in ("function", "method"):
                q = _qualified(sym)
                nid = _node_id(sym.file_path, q)
                if nid not in all_nodes:
                    all_nodes[nid] = CallNode(
                        node_id=nid,
                        name=sym.name,
                        qualified=q,
                        file_path=sym.file_path,
                        line_number=sym.line_number,
                        language=sym.language,
                        symbol_type=sym.type,
                        parent_class=sym.parent_class,
                    )

        # 1. Filter out old call edges belonging to modified/deleted files
        file_edges_map = old_edges_data.get("edges", {})
        for path in list(file_edges_map.keys()):
            if path in changed_files:
                del file_edges_map[path]

        # 2. Extract new call edges for added/modified files
        for f in files:
            path = f.get("path", "")
            if path in changed_files:
                content = f.get("content", "")
                if path and content:
                    file_edges = self.extractor.extract_call_edges(
                        path, content, defn_by_name, all_nodes
                    )
                    file_edges_map[path] = file_edges

        if files is None or not any(f.get("path") in changed_files for f in files):
            repo_path = context.repo_path if context else None
            if repo_path:
                for path in changed_files:
                    full_path = os.path.join(repo_path, path)
                    if os.path.exists(full_path):
                        try:
                            with open(
                                full_path, "r", encoding="utf-8", errors="ignore"
                            ) as fh:
                                content = fh.read()
                            file_edges = self.extractor.extract_call_edges(
                                path, content, defn_by_name, all_nodes
                            )
                            file_edges_map[path] = file_edges
                        except Exception:
                            pass

        # 3. Save updated edges map
        self.store.save_call_edges_cache(repo_name, file_edges_map)

        # 4. Combine all edges
        all_edges = []
        for edges in file_edges_map.values():
            all_edges.extend(edges)

        yield {
            "status": "building_graph",
            "message": f"Building graph ({len(all_nodes)} nodes, {len(all_edges)} edges)…",
        }

        # Build NetworkX DiGraph
        G: nx.DiGraph = nx.DiGraph()

        for nid, node in all_nodes.items():
            G.add_node(
                nid,
                name=node.name,
                qualified=node.qualified,
                file_path=node.file_path,
                line_number=node.line_number,
                language=node.language,
                symbol_type=node.symbol_type,
                parent_class=node.parent_class or "",
            )

        for caller_id, callee_id, call_line, ambiguous in all_edges:
            if caller_id in G and callee_id in G:
                if G.has_edge(caller_id, callee_id):
                    existing = G[caller_id][callee_id]
                    if call_line < existing.get("call_line", call_line):
                        G[caller_id][callee_id]["call_line"] = call_line
                else:
                    G.add_edge(
                        caller_id,
                        callee_id,
                        call_line=call_line,
                        ambiguous=ambiguous,
                        relationship="calls",
                    )

        yield {"status": "computing_metrics", "message": "Computing graph metrics…"}

        # Annotate nodes with fan-in / fan-out / recursion
        recursive_ids: List[str] = []
        entry_ids: List[str] = []

        for nid in list(G.nodes()):
            fi = G.in_degree(nid)
            fo = G.out_degree(nid)
            is_recursive = G.has_edge(nid, nid)
            is_entry = fi == 0

            G.nodes[nid]["fan_in"] = fi
            G.nodes[nid]["fan_out"] = fo
            G.nodes[nid]["is_recursive"] = is_recursive
            G.nodes[nid]["is_entry"] = is_entry

            if is_recursive:
                recursive_ids.append(nid)
            if is_entry:
                entry_ids.append(nid)

        # Re-save graph
        self.store.save_graph(repo_name, G)

        # Build and save summary
        top_fan_in = sorted(
            [{"node_id": n, "fan_in": G.in_degree(n)} for n in G.nodes()],
            key=lambda x: x["fan_in"],
            reverse=True,
        )[:10]
        top_fan_out = sorted(
            [{"node_id": n, "fan_out": G.out_degree(n)} for n in G.nodes()],
            key=lambda x: x["fan_out"],
            reverse=True,
        )[:10]

        # Aggregate summary metrics
        summary = CallGraphSummary(
            repo=repo_name,
            generated_at=datetime.now(timezone.utc).isoformat(),
            node_count=G.number_of_nodes(),
            edge_count=G.number_of_edges(),
            entry_functions=entry_ids[:50],
            recursive_functions=recursive_ids,
            top_fan_in=top_fan_in,
            top_fan_out=top_fan_out,
        )
        self.store.save_summary(repo_name, summary)

        yield {
            "status": "complete",
            "message": f"✓ Call graph built: {G.number_of_nodes()} functions, {G.number_of_edges()} calls",
        }

        return summary
