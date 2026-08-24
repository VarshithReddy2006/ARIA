"""Architecture Service.

Orchestrates the full Architecture Intelligence pipeline:
  1. Parse repository files with TreeSitterService
  2. Detect entry points with EntryPointService
  3. Build dependency graphs with GraphService
  4. Compute architecture metadata locally (no LLM)
  5. Persist graph and summary to disk

All computations are local — no Gemini calls are made in this service.
"""

import logging
import os
import time
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

from services.tree_sitter_service import TreeSitterService
from services.graph_service import GraphService
from services.entry_point_service import EntryPointService
from models.architecture import ArchitectureSummary as ArchSummary
from storage.snapshot_store import SnapshotStore
from core.cache import AnalysisCache

logger = logging.getLogger(__name__)

# Default storage directory relative to project root
_ARCH_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "architecture",
)

# Increment this whenever the summary schema or computation logic changes.
# A persisted summary with a lower version is treated as stale and rebuilt
# automatically, preventing the "zero dependencies from an old empty run"
# class of bugs.
_SUMMARY_SCHEMA_VERSION = 2


class ArchitectureService:
    """Builds and persists the architecture intelligence layer for a repository.

    This service is stateless; each call to build() operates independently.
    Results are written to disk and can be retrieved without rebuilding.
    """

    @property
    def schema_version(self) -> int:
        return _SUMMARY_SCHEMA_VERSION

    @classmethod
    def get_schema_version(cls) -> int:
        return _SUMMARY_SCHEMA_VERSION

    def __init__(
        self,
        arch_dir: str = _ARCH_DIR,
        graphs_dir: Optional[str] = None,
        snapshot_store: Optional[SnapshotStore] = None,
        analysis_cache: Optional[AnalysisCache] = None,
    ) -> None:
        """Initialise the service.

        Args:
            arch_dir:   Directory where architecture JSON summaries are saved.
            graphs_dir: Directory where graph JSON files are saved.
                        Defaults to GraphService's default when None.
            snapshot_store: Shared snapshot store instance.
            analysis_cache: Shared analysis cache instance.
        """
        self.arch_dir = arch_dir
        os.makedirs(self.arch_dir, exist_ok=True)

        if snapshot_store is None:
            if arch_dir != _ARCH_DIR:
                parent_dir = os.path.dirname(arch_dir)
                dir_name = os.path.basename(arch_dir)
                from storage.snapshot_store import JsonSnapshotStore

                self.snapshot_store = JsonSnapshotStore(
                    base_dir=parent_dir, key_map={"architecture": dir_name}
                )
            else:
                from storage.snapshot_store import JsonSnapshotStore

                self.snapshot_store = JsonSnapshotStore()
        else:
            self.snapshot_store = snapshot_store

        self.analysis_cache = analysis_cache or AnalysisCache()

        self.tree_sitter = TreeSitterService()
        self.graph_service = GraphService(
            **({"graphs_dir": graphs_dir} if graphs_dir else {})
        )
        self.entry_point_service = EntryPointService()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(
        self,
        repo_name: str,
        repo_path: Optional[str] = None,
        files: Optional[List[Dict[str, str]]] = None,
        force_rebuild: bool = False,
    ) -> Dict[str, Any]:
        """Run the full architecture build pipeline for a repository.

        Provides backward compatibility by delegating to build_full.
        """
        return self.build_full(repo_name, repo_path=repo_path, files=files)

    def build_full(
        self,
        repo_name: str,
        repo_path: Optional[str] = None,
        files: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Run the full architecture build pipeline and save parsed_files."""
        if repo_path is None and files is None:
            raise ValueError("Provide either repo_path or files.")

        logger.info("Starting full architecture build for %s", repo_name)

        parsed = self.tree_sitter.parse_repository(
            repo_path=repo_path or "",
            files=files,
        )
        logger.info("Parsed %d supported source files", len(parsed))

        if len(parsed) == 0:
            logger.error(
                "[PIPELINE:%s] architecture_service.build_full produced ZERO parsed files.",
                repo_name,
            )

        # Cache parsed files list
        parsed_files_payload = {"parsed": parsed, "_schema_version": 1}
        self.snapshot_store.save(repo_name, "parsed_files", parsed_files_payload)
        self.analysis_cache.set(repo_name, "parsed_files", parsed_files_payload, 1)

        all_paths = (
            [f["path"] for f in files] if files else self._walk_repo_paths(repo_path)
        )
        ep_result = self.entry_point_service.detect(
            all_paths, parsed, files_content=files
        )
        entry_points: List[str] = ep_result["entry_points"]

        graph = self.graph_service.build_file_graph(parsed)
        summary = self._compute_summary(
            graph=graph,
            entry_points=entry_points,
            total_files=len(all_paths),
        )

        self.graph_service.save_graph(graph, repo_name)
        self._save_summary(repo_name, summary)

        return {
            "status": "success",
            "repo": repo_name,
            "files_parsed": len(parsed),
            "dependencies_found": graph.number_of_edges(),
            "entry_points": entry_points,
            "architecture": summary,
        }

    def build_partial(
        self,
        repo_name: str,
        changed_files: Set[str],
        repo_path: Optional[str] = None,
        files: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Incrementally update parsed files and rebuild the dependency graph."""
        old_parsed_data = self.analysis_cache.get(repo_name, "parsed_files", 1)
        if old_parsed_data is None:
            old_parsed_data = self.snapshot_store.load(repo_name, "parsed_files")
            if old_parsed_data is not None:
                self.analysis_cache.set(repo_name, "parsed_files", old_parsed_data, 1)

        if old_parsed_data is None:
            logger.info(
                "No existing parsed_files cache found for %s, running full build.",
                repo_name,
            )
            return self.build_full(repo_name, repo_path=repo_path, files=files)

        if repo_path is None and files is None:
            raise ValueError("Provide either repo_path or files.")

        logger.info("Starting partial architecture build for %s", repo_name)

        # 1. Filter out parsed metadata for modified/deleted files
        old_parsed_list = old_parsed_data.get("parsed", [])
        retained_parsed = [
            p for p in old_parsed_list if p.get("file_path") not in changed_files
        ]

        # 2. Parse only the added/modified files
        new_parsed = []
        if files is not None:
            for f in files:
                path = f.get("path", "")
                if path in changed_files:
                    res = self.tree_sitter.parse_file(path, f.get("content", ""))
                    if res:
                        new_parsed.append(res)
        else:
            for path in changed_files:
                full_path = os.path.join(repo_path, path)
                if os.path.exists(full_path):
                    try:
                        with open(
                            full_path, "r", encoding="utf-8", errors="ignore"
                        ) as fh:
                            content = fh.read()
                        res = self.tree_sitter.parse_file(path, content)
                        if res:
                            new_parsed.append(res)
                    except Exception as exc:
                        logger.debug("Failed to read %s: %s", full_path, exc)

        # 3. Merge and save the updated parsed_files list
        merged_parsed = retained_parsed + new_parsed
        merged_payload = {"parsed": merged_parsed, "_schema_version": 1}
        self.snapshot_store.save(repo_name, "parsed_files", merged_payload)
        self.analysis_cache.set(repo_name, "parsed_files", merged_payload, 1)

        # 4. Detect entry points using the merged parsed files
        all_paths = (
            [f["path"] for f in files] if files else self._walk_repo_paths(repo_path)
        )
        ep_result = self.entry_point_service.detect(
            all_paths, merged_parsed, files_content=files
        )
        entry_points: List[str] = ep_result["entry_points"]

        # 5. Rebuild the graph and compute summary
        graph = self.graph_service.build_file_graph(merged_parsed)
        summary = self._compute_summary(
            graph=graph,
            entry_points=entry_points,
            total_files=len(all_paths),
        )

        # 6. Save graph and summary
        self.graph_service.save_graph(graph, repo_name)
        self._save_summary(repo_name, summary)

        logger.info(
            "Incremental architecture build complete for %s — %d retained, %d new from %d changed files",
            repo_name,
            len(retained_parsed),
            len(new_parsed),
            len(changed_files),
        )

        return {
            "status": "success",
            "repo": repo_name,
            "files_parsed": len(merged_parsed),
            "dependencies_found": graph.number_of_edges(),
            "entry_points": entry_points,
            "architecture": summary,
        }

    def get_summary(self, repo_name: str) -> Optional[ArchSummary]:
        """Load and return a persisted architecture summary.

        Args:
            repo_name: Repository identifier (owner/repo).

        Returns:
            An ArchitectureSummary Pydantic model, or None if not found.
        """
        cached = self.analysis_cache.get(
            repo_name, "architecture", _SUMMARY_SCHEMA_VERSION
        )
        if cached is not None:
            return cached

        data = self.snapshot_store.load(repo_name, "architecture")
        if data is None:
            return None

        stored_version = data.get("_schema_version", 0)
        if stored_version < _SUMMARY_SCHEMA_VERSION:
            logger.warning(
                "Discarding stale architecture summary for %s (schema v%d < current v%d)",
                repo_name,
                stored_version,
                _SUMMARY_SCHEMA_VERSION,
            )
            return None

        try:
            filtered = {k: v for k, v in data.items() if not k.startswith("_")}
            summary = ArchSummary(**filtered)
            self.analysis_cache.set(
                repo_name, "architecture", summary, _SUMMARY_SCHEMA_VERSION
            )
            return summary
        except Exception as exc:
            logger.error("Failed to deserialise architecture summary: %s", exc)
            return None

    def summary_exists(self, repo_name: str) -> bool:
        """Return True if a persisted architecture summary exists."""
        return self.snapshot_store.exists(repo_name, "architecture")

    # ------------------------------------------------------------------
    # Architecture metric computation
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_summary(
        graph: nx.DiGraph,
        entry_points: List[str],
        total_files: int,
        top_n: int = 10,
    ) -> Dict[str, Any]:
        """Compute architecture metrics purely from the graph.

        Uses NetworkX degree centrality to identify core modules and
        in/out-degree sums to identify high-coupling modules.

        Args:
            graph:       File dependency graph.
            entry_points: Detected entry point paths.
            total_files: Total number of files in the repository.
            top_n:       Number of top modules to return.

        Returns:
            Dict matching the ArchitectureSummary schema.
        """
        total_deps = graph.number_of_edges()

        if graph.number_of_nodes() == 0:
            return {
                "entry_points": entry_points,
                "core_modules": [],
                "high_coupling_modules": [],
                "total_files": total_files,
                "total_dependencies": total_deps,
            }

        from core.file_classifier import classify_file, CATEGORY_PRODUCTION

        # Degree centrality — identifies nodes that are most connected overall
        centrality = nx.degree_centrality(graph)

        # Sort prioritizing production category, then centrality score
        def _centrality_sort_key(node_score: Tuple[str, float]) -> Tuple[int, float]:
            node, score = node_score
            is_prod = 1 if classify_file(node)["category"] == CATEGORY_PRODUCTION else 0
            return (is_prod, score)

        sorted_by_centrality = sorted(
            centrality.items(), key=_centrality_sort_key, reverse=True
        )
        core_modules = [
            node for node, _ in sorted_by_centrality[:top_n] if centrality[node] > 0
        ]

        # High coupling: nodes with highest combined in-degree + out-degree
        coupling_scores = {
            node: graph.in_degree(node) + graph.out_degree(node)
            for node in graph.nodes()
        }

        def _coupling_sort_key(node_score: Tuple[str, int]) -> Tuple[int, int]:
            node, score = node_score
            is_prod = 1 if classify_file(node)["category"] == CATEGORY_PRODUCTION else 0
            return (is_prod, score)

        sorted_by_coupling = sorted(
            coupling_scores.items(), key=_coupling_sort_key, reverse=True
        )
        high_coupling = [
            node for node, score in sorted_by_coupling[:top_n] if score > 1
        ]

        return {
            "entry_points": entry_points,
            "core_modules": core_modules,
            "high_coupling_modules": high_coupling,
            "total_files": total_files,
            "total_dependencies": total_deps,
        }

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _summary_path(self, repo_name: str) -> str:
        return self.snapshot_store._get_path(repo_name, "architecture")

    def _save_summary(self, repo_name: str, summary: Dict[str, Any]) -> None:
        versioned = dict(summary)
        versioned["_schema_version"] = _SUMMARY_SCHEMA_VERSION
        versioned["_built_at"] = int(time.time())
        self.snapshot_store.save(repo_name, "architecture", versioned)

    def _load_summary(self, repo_name: str) -> Optional[Dict[str, Any]]:
        return self.snapshot_store.load(repo_name, "architecture")

    # ------------------------------------------------------------------
    # Misc helpers
    # ------------------------------------------------------------------

    _IGNORED_DIRS = {
        "node_modules",
        ".git",
        "dist",
        "build",
        ".next",
        "venv",
        "__pycache__",
        ".venv",
    }

    def _walk_repo_paths(self, repo_path: str) -> List[str]:
        """Walk repo on disk and return all relative file paths."""
        paths = []
        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in self._IGNORED_DIRS]
            for fname in files:
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, repo_path).replace(os.sep, "/")
                paths.append(rel)
        return paths
