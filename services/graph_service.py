"""Graph Service — Dependency Graph Engine.

Builds file and module dependency graphs from parsed repository metadata using
NetworkX directed graphs.

Graph types produced:
  - File Dependency Graph  : nodes = file paths, edges = import relationships
  - Module Graph           : nodes = top-level module/package names,
                             edges = module-level dependencies

Graphs are serialised to disk as pickle files under data/graphs/ so they can
be reloaded without rebuilding.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

import networkx as nx

import threading

logger = logging.getLogger(__name__)

# Default storage directory relative to the project root
_GRAPHS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "graphs",
)


class GraphService:
    """Builds, stores, and loads file and module dependency graphs."""

    def __init__(self, graphs_dir: str = _GRAPHS_DIR) -> None:
        """Initialise the service.

        Args:
            graphs_dir: Directory where graph persistence files are saved.
        """
        self.graphs_dir = graphs_dir
        os.makedirs(self.graphs_dir, exist_ok=True)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_file_graph(self, parsed_files: List[Dict[str, Any]]) -> nx.DiGraph:
        """Build a directed file dependency graph.

        Each node is a file path.  An edge A → B means file A imports from B
        (where B is resolved to an actual file in the repository).

        Args:
            parsed_files: Output of TreeSitterService.parse_repository().

        Returns:
            A NetworkX DiGraph where node attributes include *language*.
        """
        graph: nx.DiGraph = nx.DiGraph()

        # Build an index of known files for import resolution
        file_index = self._build_file_index(parsed_files)

        for pf in parsed_files:
            src = pf["file_path"]
            lang = pf.get("language", "unknown")

            if not graph.has_node(src):
                graph.add_node(src, language=lang, type="file")

            for imp in pf.get("imports", []):
                resolved = self._resolve_import(imp, src, file_index, lang)
                if resolved:
                    if not graph.has_node(resolved):
                        resolved_lang = file_index.get(resolved, {}).get(
                            "language", "unknown"
                        )
                        graph.add_node(resolved, language=resolved_lang, type="file")
                    graph.add_edge(src, resolved, relationship="imports")

        logger.info(
            "File dependency graph built: %d nodes, %d edges",
            graph.number_of_nodes(),
            graph.number_of_edges(),
        )
        return graph

    def build_module_graph(self, parsed_files: List[Dict[str, Any]]) -> nx.DiGraph:
        """Build a directed module dependency graph.

        Each node is a top-level module/package name (e.g. 'fastapi', 'os').
        Edges represent which module imports which other module.

        Args:
            parsed_files: Output of TreeSitterService.parse_repository().

        Returns:
            A NetworkX DiGraph with module-level granularity.
        """
        graph: nx.DiGraph = nx.DiGraph()

        for pf in parsed_files:
            src_module = self._file_to_module(pf["file_path"])
            if not graph.has_node(src_module):
                graph.add_node(src_module, type="module")

            for imp in pf.get("imports", []):
                dep_module = self._import_to_top_module(imp)
                if not graph.has_node(dep_module):
                    graph.add_node(dep_module, type="module")
                graph.add_edge(src_module, dep_module, relationship="depends_on")

        logger.info(
            "Module graph built: %d nodes, %d edges",
            graph.number_of_nodes(),
            graph.number_of_edges(),
        )
        return graph

    def get_graph_stats(self, graph: nx.DiGraph) -> Dict[str, Any]:
        """Return basic statistics about a dependency graph.

        Args:
            graph: Any NetworkX DiGraph.

        Returns:
            Dict with node_count, edge_count, density, and is_dag flag.
        """
        return {
            "node_count": graph.number_of_nodes(),
            "edge_count": graph.number_of_edges(),
            "density": round(nx.density(graph), 6),
            "is_dag": nx.is_directed_acyclic_graph(graph),
        }

    def get_cycles(self, repo_name: str) -> List[List[str]]:
        """Return elementary cycles in the repository dependency graph."""
        graph = self.load_graph(repo_name)
        if graph is None or graph.number_of_nodes() == 0:
            return []
        try:
            return list(nx.simple_cycles(graph))
        except Exception as exc:
            logger.warning("Failed to compute cycles for %s: %s", repo_name, exc)
            return []

    def get_strongly_connected_components_count(self, repo_name: str) -> int:
        """Return count of strongly connected components in the repository graph."""
        graph = self.load_graph(repo_name)
        if graph is None or graph.number_of_nodes() == 0:
            return 0
        return nx.number_strongly_connected_components(graph)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_graph(self, graph: nx.DiGraph, repo_name: str) -> str:
        """Persist a graph to disk as a safe schema-versioned JSON file.

        Args:
            graph: The NetworkX graph to serialise.
            repo_name: Repository identifier (owner/repo). Slashes are
                       replaced with underscores in the filename.

        Returns:
            Absolute path to the saved JSON file.
        """
        safe_name = repo_name.replace("/", "_")
        path = os.path.join(self.graphs_dir, f"{safe_name}.json")
        payload = {
            "schema_version": 1,
            "repo_name": repo_name,
            "graph_data": nx.node_link_data(graph),
        }
        with self._lock:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
        logger.info("Graph saved to %s", path)
        return path

    def load_graph(self, repo_name: str) -> Optional[nx.DiGraph]:
        """Load a previously persisted graph from disk.

        Args:
            repo_name: Repository identifier (owner/repo).

        Returns:
            The loaded DiGraph, or None if no file exists.
        """
        safe_name = repo_name.replace("/", "_")
        json_path = os.path.join(self.graphs_dir, f"{safe_name}.json")
        pkl_path = os.path.join(self.graphs_dir, f"{safe_name}.pkl")

        with self._lock:
            # Safely purge legacy .pkl file if present
            if os.path.exists(pkl_path):
                logger.warning(
                    "Purging legacy pickle graph file %s for security reasons.",
                    pkl_path,
                )
                try:
                    os.remove(pkl_path)
                except Exception as exc:
                    logger.warning(
                        "Could not remove legacy pickle file %s: %s", pkl_path, exc
                    )

            if not os.path.exists(json_path):
                return None

            try:
                with open(json_path, "r", encoding="utf-8") as fh:
                    payload = json.load(fh)
                graph_data = (
                    payload.get("graph_data", payload)
                    if isinstance(payload, dict)
                    else payload
                )
                if isinstance(graph_data, dict):
                    if "edges" in graph_data and "links" not in graph_data:
                        graph_data["links"] = graph_data["edges"]
                    if "nodes" not in graph_data:
                        graph_data["nodes"] = []
                    if "links" not in graph_data:
                        graph_data["links"] = []
                graph = nx.node_link_graph(graph_data)
                logger.info("Graph loaded from %s", json_path)
                return graph
            except Exception as exc:
                logger.error("Failed to load graph from %s: %s", json_path, exc)
                return None

    def graph_exists(self, repo_name: str) -> bool:
        """Return True if a persisted graph file exists for the given repo."""
        safe_name = repo_name.replace("/", "_")
        json_path = os.path.join(self.graphs_dir, f"{safe_name}.json")
        return os.path.exists(json_path)

    def get_visualization_graph(
        self,
        repo_name: str,
        architecture_service,
        search_query: Optional[str] = None,
        max_nodes: int = 500,
        max_edges: int = 2000,
    ) -> Dict[str, Any]:
        """Expose dependency graph data to the frontend, applying clustering, limits, and searching.

        Args:
            repo_name:            Repository identifier (owner/repo).
            architecture_service: ArchitectureService to retrieve summaries.
            search_query:         Query search filter term.
            max_nodes:            Max nodes limit.
            max_edges:            Max edges limit.

        Returns:
            A dictionary with nodes and edges formatted for React Flow.
        """
        # 1. Load graph
        graph = self.load_graph(repo_name)
        if graph is None or graph.number_of_nodes() == 0:
            return {"nodes": [], "edges": []}

        # 2. Get architecture summary sets
        summary = architecture_service.get_summary(repo_name)
        entry_set = set(summary.entry_points if summary else [])
        core_set = set(summary.core_modules if summary else [])
        coupling_set = set(summary.high_coupling_modules if summary else [])

        # 3. Collapse/Cluster nodes (tests/*, docs/*, examples/*)
        def get_collapsed_id(node_id: str) -> str:
            norm = node_id.replace("\\", "/").lower()
            if norm.startswith("tests/") or norm == "tests":
                return "tests/"
            if norm.startswith("docs/") or norm == "docs":
                return "docs/"
            if norm.startswith("examples/") or norm == "examples":
                return "examples/"
            return node_id

        # Construct collapsed graph
        collapsed_graph = nx.DiGraph()

        # Track original properties for grouped nodes
        collapsed_labels = {
            "tests/": "tests/",
            "docs/": "docs/",
            "examples/": "examples/",
        }

        for node, attrs in graph.nodes(data=True):
            collapsed_id = get_collapsed_id(node)
            if not collapsed_graph.has_node(collapsed_id):
                if collapsed_id in collapsed_labels:
                    collapsed_graph.add_node(
                        collapsed_id,
                        label=collapsed_labels[collapsed_id],
                        category="directory",
                        language="directory",
                    )
                else:
                    # Determine node category
                    if node in entry_set:
                        cat = "entry_point"
                    elif node in core_set:
                        cat = "core_module"
                    elif node in coupling_set:
                        cat = "high_coupling"
                    else:
                        cat = "regular"

                    collapsed_graph.add_node(
                        collapsed_id,
                        label=os.path.basename(node),
                        category=cat,
                        language=attrs.get("language", "unknown"),
                    )

        # Map edges to collapsed nodes
        for u, v, edge_attrs in graph.edges(data=True):
            c_u = get_collapsed_id(u)
            c_v = get_collapsed_id(v)
            if c_u != c_v:
                collapsed_graph.add_edge(
                    c_u, c_v, relationship=edge_attrs.get("relationship", "imports")
                )

        # 4. Search Filter
        active_graph = collapsed_graph
        if search_query:
            search_query_lower = search_query.lower()
            nodes_to_keep = set()
            for n in collapsed_graph.nodes():
                # Match label or full path
                label = collapsed_graph.nodes[n].get("label", "")
                if (
                    search_query_lower in n.lower()
                    or search_query_lower in label.lower()
                ):
                    nodes_to_keep.add(n)
                    # Add immediate predecessors and successors
                    nodes_to_keep.update(collapsed_graph.predecessors(n))
                    nodes_to_keep.update(collapsed_graph.successors(n))
            active_graph = collapsed_graph.subgraph(nodes_to_keep)

        # 5. Calculate degree and centrality on active_graph
        node_degrees = dict(active_graph.degree())
        node_centrality = {}
        if active_graph.number_of_nodes() > 1:
            node_centrality = nx.degree_centrality(active_graph)
        else:
            node_centrality = {n: 0.0 for n in active_graph.nodes()}

        # 6. Apply limits (max_nodes = 500)
        # Prioritize entry points, core modules, high coupling, directories, then regular
        # Sort key: (category_score, centrality, degree)
        cat_priority = {
            "entry_point": 4,
            "core_module": 3,
            "high_coupling": 2,
            "directory": 1,
            "regular": 0,
        }

        def get_node_priority(n: str) -> tuple:
            cat = active_graph.nodes[n].get("category", "regular")
            return (
                cat_priority.get(cat, 0),
                node_centrality.get(n, 0.0),
                node_degrees.get(n, 0),
            )

        sorted_nodes = sorted(active_graph.nodes(), key=get_node_priority, reverse=True)
        top_nodes = sorted_nodes[:max_nodes]
        final_graph = active_graph.subgraph(top_nodes)

        # Compile final lists
        res_nodes = []
        for n in final_graph.nodes():
            attrs = final_graph.nodes[n]
            res_nodes.append(
                {
                    "id": n,
                    "label": attrs.get("label", n),
                    "category": attrs.get("category", "regular"),
                    "degree": node_degrees.get(n, 0),
                    "centrality": round(node_centrality.get(n, 0.0), 4),
                }
            )

        res_edges = []
        edge_count = 0
        for u, v, edge_attrs in final_graph.edges(data=True):
            if edge_count >= max_edges:
                break
            res_edges.append(
                {
                    "source": u,
                    "target": v,
                    "relationship": edge_attrs.get("relationship", "imports"),
                }
            )
            edge_count += 1

        return {"nodes": res_nodes, "edges": res_edges}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_file_index(
        parsed_files: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """Map file paths to their parsed metadata for fast lookup."""
        return {pf["file_path"]: pf for pf in parsed_files}

    @staticmethod
    def _resolve_import(
        imp: str,
        source_file: str,
        file_index: Dict[str, Dict[str, Any]],
        language: str,
    ) -> Optional[str]:
        """Attempt to resolve an import string to a file path in the repo.

        Strategy:
        1. Convert dotted module path → relative file candidate (Python).
        2. Convert JS/TS relative path → normalised path.
        3. If the resolved path (with common extensions) exists in the index,
           return it.  Otherwise return None (external dependency).
        """
        if language == "python":
            return GraphService._resolve_python_import(imp, source_file, file_index)
        else:
            return GraphService._resolve_js_import(imp, source_file, file_index)

    @staticmethod
    def _resolve_python_import(
        imp: str, source_file: str, file_index: Dict[str, Any]
    ) -> Optional[str]:
        """Resolve a Python dotted import to a repo file path."""
        candidates = []

        # Absolute dotted path → path/to/module.py  or path/to/module/__init__.py
        rel_path = imp.replace(".", "/")
        candidates.append(rel_path + ".py")
        candidates.append(rel_path + "/__init__.py")

        # Relative: try from the same directory as the source file
        source_dir = "/".join(source_file.split("/")[:-1])
        if source_dir:
            candidates.append(source_dir + "/" + rel_path + ".py")
            candidates.append(source_dir + "/" + rel_path + "/__init__.py")

        for c in candidates:
            # Normalise simple double-slashes
            c = c.replace("//", "/")
            if c in file_index:
                return c
        return None

    @staticmethod
    def _resolve_js_import(
        imp: str, source_file: str, file_index: Dict[str, Any]
    ) -> Optional[str]:
        """Resolve a JS/TS import specifier to a repo file path."""
        # Non-relative → external package, skip
        if not imp.startswith("."):
            return None

        source_dir = "/".join(source_file.split("/")[:-1])
        # Combine source dir + relative import, normalise
        combined = (source_dir + "/" + imp).replace("//", "/")

        # Strip leading ./
        parts = []
        for part in combined.split("/"):
            if part == "..":
                if parts:
                    parts.pop()
            elif part and part != ".":
                parts.append(part)
        base = "/".join(parts)

        extensions = [".ts", ".tsx", ".js", ".jsx", "/index.ts", "/index.js"]
        # If imp already has an extension, try as-is first
        if "." in imp.split("/")[-1]:
            if base in file_index:
                return base
        for ext in extensions:
            candidate = base + ext
            if candidate in file_index:
                return candidate
        return None

    @staticmethod
    def _file_to_module(file_path: str) -> str:
        """Convert a file path to a dotted module name (best effort)."""
        # Remove extension
        without_ext = os.path.splitext(file_path)[0]
        # Replace path separators with dots
        module = without_ext.replace("/", ".").replace("\\", ".")
        # Strip __init__ suffix
        if module.endswith(".__init__"):
            module = module[: -len(".__init__")]
        return module

    @staticmethod
    def _import_to_top_module(imp: str) -> str:
        """Return the top-level package name from an import string."""
        # For relative JS imports like './foo/bar' keep as-is (they're internal)
        if imp.startswith("."):
            return imp.split("/")[0] if "/" in imp else imp
        # For dotted Python imports return first segment
        return imp.split(".")[0]
