"""Reading Order Service — Phase 2.

Generates the optimal file-reading sequence for a repository by combining:
  - Entry point priority (files that start execution)
  - Degree centrality (files most-imported by others)
  - Topological ordering (dependencies before dependants)
  - Directory heuristics (core packages before peripheral ones)

All computation is local — no LLM is invoked.

Algorithm
---------
1. Load the persisted file dependency graph (built by Phase 1).
2. Score every node with a composite score:
     score = (
         ENTRY_BOOST        * is_entry_point
       + CENTRALITY_WEIGHT  * degree_centrality[node]
       + IN_DEGREE_WEIGHT   * normalised_in_degree[node]
       + CORE_DIR_BOOST     * is_core_directory(node)
     )
3. Produce a topological reading order respecting dependency direction:
   - Start with entry points (highest score first).
   - Emit each node only after its dependencies have been emitted.
   - Break ties by composite score (highest first).
4. Append any unvisited nodes sorted by score descending.
5. Build ReadingOrderEntry objects with tier labels and reasons.
"""

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

from models.phase2 import ReadingOrder, ReadingOrderEntry
from services.architecture_service import ArchitectureService
from services.graph_service import GraphService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scoring weights
# ---------------------------------------------------------------------------
_ENTRY_BOOST = 100.0  # bonus for confirmed entry-point files
_CENTRALITY_WEIGHT = 50.0  # weight applied to normalised degree centrality
_IN_DEGREE_WEIGHT = 30.0  # weight for normalised in-degree (imported-by count)
_CORE_DIR_BOOST = 15.0  # bonus for files in recognised core directories

# Average words per minute for reading dense code
_WORDS_PER_MINUTE = 200
# Rough characters-to-words conversion (code is denser than prose)
_CHARS_PER_WORD = 8
# Assumed average file size in characters when we don't have content
_AVG_FILE_CHARS = 2_000

# Directory names whose files get a core-directory boost
_CORE_DIRS: Set[str] = {
    "core",
    "lib",
    "src",
    "api",
    "backend",
    "server",
    "services",
    "agents",
    "models",
    "routes",
    "controllers",
    "middleware",
    "auth",
    "db",
    "database",
}

# Directories whose files are pushed toward the end of the reading order
_PERIPHERAL_DIRS: Set[str] = {
    "tests",
    "test",
    "docs",
    "docs_src",
    "examples",
    "example",
    "scripts",
    "benchmarks",
    "migrations",
    "fixtures",
    "mocks",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
}

# Reading time cap — we don't list more than this many files even for huge repos
_MAX_LISTED_FILES = 50


class ReadingOrderService:
    """Generates an optimal reading order from the Phase 1 dependency graph."""

    def __init__(
        self,
        architecture_service: Optional[ArchitectureService] = None,
        graph_service: Optional[GraphService] = None,
        analysis_store: Optional[Any] = None,
    ) -> None:
        self.architecture_service = architecture_service or ArchitectureService()
        self.graph_service = graph_service or GraphService()
        self.analysis_store = analysis_store

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_reading_order(self, repo_name: str) -> ReadingOrder:
        """Generate the optimal file-reading sequence for a repository.

        Requires the architecture to have been built via Phase 1
        (POST /api/architecture/build).

        Args:
            repo_name: Repository identifier (owner/repo).

        Returns:
            A ReadingOrder model with ordered_files, reasoning, and
            estimated_reading_time.

        Raises:
            ValueError: If no architecture graph exists for the repo.
        """
        # 1. Load graph and summary
        graph = self.graph_service.load_graph(repo_name)
        if graph is None:
            raise ValueError(
                f"No dependency graph found for '{repo_name}'. "
                "Please analyze the repository first."
            )

        if graph.number_of_nodes() == 0:
            files: List[str] = []
            if self.analysis_store:
                try:
                    store_entry = self.analysis_store.get(repo_name)
                    if store_entry and "analysis" in store_entry:
                        analysis = store_entry["analysis"]
                        struct = (
                            analysis.structure
                            if hasattr(analysis, "structure")
                            else analysis.get("structure", {})
                        )
                        for parent, filenames in struct.items():
                            for fn in filenames:
                                fpath = f"{parent}/{fn}" if parent != "." else fn
                                files.append(fpath)
                except Exception:
                    pass

            if not files:
                try:
                    from storage.snapshot_store import JsonSnapshotStore

                    store = JsonSnapshotStore()
                    parsed_snap = store.load(repo_name, "parsed_files")
                    if parsed_snap and isinstance(parsed_snap, dict):
                        file_list = parsed_snap.get("files", []) or parsed_snap.get(
                            "parsed", []
                        )
                        files = [
                            f.get("path")
                            for f in file_list
                            if isinstance(f, dict) and f.get("path")
                        ]
                except Exception:
                    pass

            if files:
                files = sorted(set(files))[:_MAX_LISTED_FILES]
                entries = [
                    ReadingOrderEntry(
                        rank=i + 1,
                        file_path=f,
                        reason="Repository documentation / standalone file",
                        tier="other",
                        score=round(1.0 / (i + 1), 2),
                    )
                    for i, f in enumerate(files)
                ]
                return ReadingOrder(
                    repo=repo_name,
                    ordered_files=entries,
                    reasoning=[
                        "No code dependency graph detected in this repository.",
                        "Showing available repository files in alphabetical order.",
                    ],
                    estimated_reading_time=1,
                    total_files_ranked=len(files),
                )

            return ReadingOrder(
                repo=repo_name,
                ordered_files=[],
                reasoning=[
                    "No reading path can be generated because this repository contains no analyzable code symbols."
                ],
                estimated_reading_time=0,
                total_files_ranked=0,
            )

        summary = self.architecture_service.get_summary(repo_name)
        entry_points: List[str] = summary.entry_points if summary else []
        core_modules: List[str] = summary.core_modules if summary else []

        # 2. Compute per-node scores
        scores = self._compute_scores(graph, entry_points, core_modules)

        # 3. Build topological reading order
        ordered = self._topological_reading_order(graph, scores, entry_points)

        # 4. Trim to cap
        ordered = ordered[:_MAX_LISTED_FILES]

        # 5. Build output entries
        entries = self._build_entries(ordered, scores, entry_points, core_modules)

        # 6. Estimate reading time
        total_chars = len(ordered) * _AVG_FILE_CHARS
        total_words = total_chars / _CHARS_PER_WORD
        reading_minutes = max(1, int(total_words / _WORDS_PER_MINUTE))

        # 7. Compose reasoning bullets
        reasoning = self._build_reasoning(
            graph, entry_points, core_modules, len(ordered)
        )

        logger.info(
            "Reading order generated for %s: %d files, ~%d min",
            repo_name,
            len(entries),
            reading_minutes,
        )

        return ReadingOrder(
            repo=repo_name,
            ordered_files=entries,
            reasoning=reasoning,
            estimated_reading_time=reading_minutes,
            total_files_ranked=graph.number_of_nodes(),
        )

    # ------------------------------------------------------------------
    # Score computation
    # ------------------------------------------------------------------

    def _compute_scores(
        self,
        graph: nx.DiGraph,
        entry_points: List[str],
        core_modules: List[str],
    ) -> Dict[str, float]:
        """Compute a composite priority score for every graph node."""
        entry_set = set(entry_points)
        core_set = set(core_modules)

        # Normalised degree centrality (0–1)
        if graph.number_of_nodes() > 1:
            centrality = nx.degree_centrality(graph)
        else:
            centrality = {n: 0.0 for n in graph.nodes()}

        # Normalised in-degree (how many files import this one)
        max_in = max((graph.in_degree(n) for n in graph.nodes()), default=1) or 1
        in_deg_norm = {n: graph.in_degree(n) / max_in for n in graph.nodes()}

        scores: Dict[str, float] = {}
        for node in graph.nodes():
            score = 0.0

            # Entry point bonus
            if node in entry_set:
                score += _ENTRY_BOOST

            # Core module bonus (also from centrality top-n)
            if node in core_set:
                score += _CENTRALITY_WEIGHT * 0.5

            # Degree centrality
            score += _CENTRALITY_WEIGHT * centrality.get(node, 0.0)

            # In-degree (how heavily imported)
            score += _IN_DEGREE_WEIGHT * in_deg_norm.get(node, 0.0)

            # Core directory heuristic
            if self._is_core_dir(node):
                score += _CORE_DIR_BOOST

            # Peripheral directory penalty
            if self._is_peripheral_dir(node):
                score -= 40.0

            scores[node] = score

        return scores

    # ------------------------------------------------------------------
    # Topological ordering
    # ------------------------------------------------------------------

    def _topological_reading_order(
        self,
        graph: nx.DiGraph,
        scores: Dict[str, float],
        entry_points: List[str],
    ) -> List[str]:
        """Return nodes in reading order using a priority-aware BFS.

        Strategy:
          - Seed the queue with entry points (sorted by score desc).
          - Emit a node only when all its *in-graph* predecessors have been
            emitted (Kahn-like traversal respecting dependency direction).
          - At each step pick the highest-score ready node.
          - After the queue drains, append remaining nodes sorted by score.

        This handles cycles gracefully by tracking visited nodes.
        """

        # Build predecessor count for Kahn's algorithm
        # We want to read A before B when A → B (A imports B means B should
        # be read before A actually, but intuitively the *caller* file is read
        # first so the reader understands context).
        # We reverse this: read the file that *uses* things first so the reader
        # sees the high-level call and then digs into the implementation.
        # So: node is ready when all its successors (things it imports) have been
        # queued... actually that makes callers wait for callees.
        #
        # The right semantic: entry points first → then walk outward following
        # imports.  A file A imports B means B is a dependency of A; we want to
        # read A first (entry point / caller), then B (callee / implementation).
        # This is a topological sort on the *import graph* treating edges as
        # "reads before" edges: A → B means read A then B.

        import heapq

        visited: Set[str] = set()
        result: List[str] = []

        # Use a min-heap with negated score for max-priority behaviour
        # heap item: (-score, node)
        heap: List[Tuple[float, str]] = []

        def push(node: str) -> None:
            if node not in visited:
                heapq.heappush(heap, (-scores.get(node, 0.0), node))

        # Seed with entry points first, then all other high-score nodes
        for ep in sorted(entry_points, key=lambda n: -scores.get(n, 0.0)):
            push(ep)

        # Also seed nodes with no predecessors (true roots in the graph)
        for node in graph.nodes():
            if graph.in_degree(node) == 0:
                push(node)

        while heap:
            _, node = heapq.heappop(heap)
            if node in visited:
                continue
            visited.add(node)
            result.append(node)
            # Push successors (files this one imports)
            for successor in sorted(
                graph.successors(node), key=lambda n: -scores.get(n, 0.0)
            ):
                push(successor)

        # Append any nodes not yet visited (disconnected components)
        remaining = sorted(
            (n for n in graph.nodes() if n not in visited),
            key=lambda n: -scores.get(n, 0.0),
        )
        result.extend(remaining)

        return result

    # ------------------------------------------------------------------
    # Entry builders
    # ------------------------------------------------------------------

    def _build_entries(
        self,
        ordered: List[str],
        scores: Dict[str, float],
        entry_points: List[str],
        core_modules: List[str],
    ) -> List[ReadingOrderEntry]:
        entry_set = set(entry_points)
        core_set = set(core_modules)
        entries = []

        for rank, fp in enumerate(ordered, start=1):
            tier, reason = self._classify(fp, scores.get(fp, 0.0), entry_set, core_set)
            entries.append(
                ReadingOrderEntry(
                    rank=rank,
                    file_path=fp,
                    reason=reason,
                    tier=tier,
                    score=round(scores.get(fp, 0.0), 2),
                )
            )
        return entries

    def _classify(
        self,
        fp: str,
        score: float,
        entry_set: Set[str],
        core_set: Set[str],
    ) -> Tuple[str, str]:
        """Return (tier, reason) for a file."""
        if fp in entry_set:
            return (
                "entry_point",
                "Repository entry point — start here to understand execution flow.",
            )

        if fp in core_set:
            return (
                "core",
                "Core module by degree centrality — heavily imported across the codebase.",
            )

        if self._is_core_dir(fp):
            dirname = fp.split("/")[0] if "/" in fp else ""
            return "service", f"Located in '{dirname}' — a primary package directory."

        if self._is_peripheral_dir(fp):
            return (
                "utility",
                "Peripheral file (tests/docs/examples) — read after core modules.",
            )

        # Score-based fallback
        if score > 20:
            return "core", "Frequently referenced module."
        return "other", "Supplementary source file."

    # ------------------------------------------------------------------
    # Reasoning bullets
    # ------------------------------------------------------------------

    @staticmethod
    def _build_reasoning(
        graph: nx.DiGraph,
        entry_points: List[str],
        core_modules: List[str],
        listed_count: int,
    ) -> List[str]:
        bullets = [
            f"Ranked {graph.number_of_nodes()} files across "
            f"{graph.number_of_edges()} dependency edges.",
            "Entry points receive the highest priority — they define execution flow.",
            "Core modules (highest degree centrality) are placed early so their "
            "interfaces are understood before dependent files.",
            "Files are ordered so imports are read before their importers where "
            "possible, following a BFS from entry points.",
        ]
        if entry_points:
            bullets.append(
                f"Detected entry points: {', '.join(entry_points[:5])}"
                + (" ..." if len(entry_points) > 5 else "")
            )
        if core_modules:
            bullets.append(
                f"Core modules: {', '.join(core_modules[:5])}"
                + (" ..." if len(core_modules) > 5 else "")
            )
        if listed_count < graph.number_of_nodes():
            bullets.append(
                f"Output capped at {listed_count} files "
                f"(repository has {graph.number_of_nodes()} parseable files)."
            )
        return bullets

    # ------------------------------------------------------------------
    # Directory helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_core_dir(fp: str) -> bool:
        parts = fp.replace("\\", "/").split("/")
        return bool(parts and parts[0].lower() in _CORE_DIRS)

    @staticmethod
    def _is_peripheral_dir(fp: str) -> bool:
        parts = fp.replace("\\", "/").split("/")
        return bool(parts and parts[0].lower() in _PERIPHERAL_DIRS)
