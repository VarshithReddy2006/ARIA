"""Impact Analysis Service — Phase 2.

Predicts which repository files are affected by a proposed change (GitHub issue,
feature request, bug report) by combining:
  1. IssueMapper keyword extraction   — parse the issue for relevant terms
  2. Semantic file matching           — keyword → file path fuzzy matching
     against the known file list (no LLM call needed when Chroma is unavailable)
  3. Forward graph traversal          — walk the import graph from seed files
     to find direct dependants
  4. Reverse graph traversal          — walk backwards to find files that
     import the seed files (they will need updating too)
  5. Risk scoring                     — high-coupling + core module hits → high risk

Architecture context is loaded from the Phase 1 persisted summary to enrich
the risk calculation without calling an LLM.
"""

import logging
import os
import re
from typing import Dict, List, Optional, Set, Tuple

import networkx as nx

from models.phase2 import DependencyPath, ImpactAnalysis
from services.architecture_service import ArchitectureService
from services.graph_service import GraphService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Risk thresholds
# ---------------------------------------------------------------------------
_HIGH_RISK_FILE_THRESHOLD = 10  # total affected files ≥ this → high
_MED_RISK_FILE_THRESHOLD = 4  # total affected files ≥ this → medium
_CORE_MODULE_HIT_MULTIPLIER = 2  # each core module hit adds 2 to risk score
_HIGH_COUPLING_HIT_MULTIPLIER = 1  # each high-coupling hit adds 1 to risk score

# Maximum BFS depth for forward/reverse traversal
_MAX_TRAVERSAL_DEPTH = 4

# How many dependency paths to report in output
_MAX_PATHS = 5

# Component detection: directory/filename → component label
_COMPONENT_MAP: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"auth|oauth|login|token|jwt|session", re.I), "Authentication"),
    (re.compile(r"api|route|endpoint|controller|view", re.I), "API Layer"),
    (
        re.compile(r"db|database|model|migration|schema|orm|sql|chroma|sqlite", re.I),
        "Database",
    ),
    (
        re.compile(r"front|ui|component|page|template|html|css|tsx|jsx", re.I),
        "Frontend",
    ),
    (re.compile(r"service|retriev|embed|chunk|github|mcp", re.I), "Services"),
    (re.compile(r"model|schema|pydantic|dataclass", re.I), "Models"),
    (re.compile(r"agent|evaluat|explainer|analyzer|mapper", re.I), "Agents"),
    (re.compile(r"memory|cache|store|chroma", re.I), "Memory"),
    (re.compile(r"test|spec|fixture|mock", re.I), "Tests"),
]


class ImpactAnalysisService:
    """Predicts change impact by combining keyword matching and graph traversal."""

    def __init__(
        self,
        architecture_service: Optional[ArchitectureService] = None,
        graph_service: Optional[GraphService] = None,
    ) -> None:
        self.architecture_service = architecture_service or ArchitectureService()
        self.graph_service = graph_service or GraphService()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_change(
        self,
        repo_name: str,
        issue_text: str,
    ) -> ImpactAnalysis:
        """Predict which files are affected by a proposed change.

        Args:
            repo_name:   Repository identifier (owner/repo).
            issue_text:  Free-text description of the change (GitHub issue,
                         feature request, commit message, etc.).

        Returns:
            An ImpactAnalysis model with directly/indirectly affected files,
            risk level, dependency paths, and confidence score.

        Raises:
            ValueError: If no architecture graph exists for the repo.
        """
        # 1. Load graph and architecture summary
        graph = self.graph_service.load_graph(repo_name)
        if graph is None:
            raise ValueError(
                f"No dependency graph found for '{repo_name}'. "
                "Please analyze the repository first."
            )

        if graph.number_of_nodes() == 0:
            return ImpactAnalysis(
                repo=repo_name,
                issue_text=issue_text,
                directly_affected_files=[],
                indirectly_affected_files=[],
                affected_components=[],
                risk_level="low",
                estimated_file_count=0,
                dependency_paths=[],
                confidence=0,
            )

        summary = self.architecture_service.get_summary(repo_name)
        core_set: Set[str] = set(summary.core_modules if summary else [])
        coupling_set: Set[str] = set(summary.high_coupling_modules if summary else [])
        entry_set: Set[str] = set(summary.entry_points if summary else [])

        # 2. Extract keywords from the issue text
        keywords = self._extract_keywords(issue_text)
        logger.info("Impact analysis for %s | keywords: %s", repo_name, keywords)

        # 3. Find seed files — files whose paths match issue keywords
        seed_files = self._match_files_to_keywords(graph, keywords, issue_text)
        logger.info("Seed files: %s", seed_files)

        # 4. Forward traversal — what does the seed import?
        #    (files the seed depends on — they may need API-compatible changes)
        forward_affected: Set[str] = set()
        for seed in seed_files:
            forward_affected.update(
                self._bfs(graph, seed, direction="forward", depth=_MAX_TRAVERSAL_DEPTH)
            )
        forward_affected -= set(seed_files)

        # 5. Reverse traversal — what imports the seed?
        #    (files that consume the seed — they may break if the seed changes)
        reverse_affected: Set[str] = set()
        for seed in seed_files:
            reverse_affected.update(
                self._bfs(graph, seed, direction="reverse", depth=_MAX_TRAVERSAL_DEPTH)
            )
        reverse_affected -= set(seed_files)

        # 6. Classify direct vs indirect
        # Direct: the seed files themselves + their immediate predecessors/successors
        direct_immediate: Set[str] = set(seed_files)
        for seed in seed_files:
            direct_immediate.update(graph.predecessors(seed))
            direct_immediate.update(graph.successors(seed))

        directly_affected = sorted(direct_immediate)
        indirectly_affected = sorted(
            (forward_affected | reverse_affected) - direct_immediate
        )

        # 7. Build dependency paths for the most impactful seeds
        dep_paths = self._build_dependency_paths(
            graph, seed_files, reverse_affected, max_paths=_MAX_PATHS
        )

        # 8. Detect affected components
        all_affected = list(direct_immediate) + indirectly_affected
        affected_components = self._detect_components(all_affected)

        # 9. Risk scoring
        risk_level, confidence = self._compute_risk(
            seed_files=list(direct_immediate),
            indirectly_affected=indirectly_affected,
            core_set=core_set,
            coupling_set=coupling_set,
            entry_set=entry_set,
            total_graph_nodes=graph.number_of_nodes(),
        )

        total_affected = len(directly_affected) + len(indirectly_affected)

        logger.info(
            "Impact analysis complete for %s: %d direct, %d indirect, risk=%s",
            repo_name,
            len(directly_affected),
            len(indirectly_affected),
            risk_level,
        )

        return ImpactAnalysis(
            repo=repo_name,
            issue_text=issue_text,
            directly_affected_files=directly_affected,
            indirectly_affected_files=indirectly_affected,
            affected_components=affected_components,
            risk_level=risk_level,
            estimated_file_count=total_affected,
            dependency_paths=dep_paths,
            confidence=confidence,
        )

    # ------------------------------------------------------------------
    # Keyword extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_keywords(text: str) -> List[str]:
        """Extract meaningful keywords from the issue text.

        Strips common stop words and short tokens, then deduplicates.
        Returns lowercase tokens sorted by length (longer = more specific).
        """
        _STOP = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "to",
            "of",
            "and",
            "or",
            "in",
            "for",
            "on",
            "with",
            "at",
            "by",
            "from",
            "as",
            "this",
            "that",
            "it",
            "its",
            "we",
            "our",
            "add",
            "fix",
            "bug",
            "issue",
            "feature",
            "update",
            "change",
            "when",
            "how",
            "what",
            "which",
            "where",
            "who",
            "can",
            "will",
            "should",
            "need",
            "needs",
            "want",
            "wants",
            "make",
            "use",
            "into",
            "also",
            "just",
            "not",
            "have",
            "has",
            "but",
            "so",
        }
        raw = re.sub(r"[^a-zA-Z0-9_\-/]", " ", text.lower())
        tokens = [t for t in raw.split() if len(t) >= 4 and t not in _STOP]
        # Deduplicate preserving order
        seen: Set[str] = set()
        result = []
        for t in tokens:
            if t not in seen:
                seen.add(t)
                result.append(t)
        return sorted(result, key=len, reverse=True)[:20]

    # ------------------------------------------------------------------
    # File matching
    # ------------------------------------------------------------------

    def _match_files_to_keywords(
        self,
        graph: nx.DiGraph,
        keywords: List[str],
        full_text: str,
    ) -> List[str]:
        """Match graph nodes (file paths) against issue keywords.

        Uses simple substring matching on the normalised file path.
        Returns up to 10 seed files sorted by match score.
        """
        all_files = list(graph.nodes())
        scored: Dict[str, int] = {}

        for fp in all_files:
            fp_norm = fp.lower().replace("\\", "/").replace("_", "-").replace(".", "-")
            score = 0
            for kw in keywords:
                kw_norm = kw.replace("_", "-").replace(".", "-")
                if kw_norm in fp_norm:
                    # Longer keyword matches are worth more
                    score += len(kw)
            if score > 0:
                scored[fp] = score

        # Also promote files that share a directory name with the keywords
        for kw in keywords:
            for fp in all_files:
                parts = fp.replace("\\", "/").split("/")
                if any(kw in p.lower() for p in parts):
                    scored[fp] = scored.get(fp, 0) + len(kw) // 2

        sorted_files = sorted(scored.items(), key=lambda x: x[1], reverse=True)
        seeds = [fp for fp, _ in sorted_files[:10]]

        # Fallback: if nothing matched, return entry-point-like files
        if not seeds:
            seeds = [
                fp
                for fp in all_files
                if os.path.basename(fp)
                in {"main.py", "api.py", "app.py", "__main__.py"}
            ][:5]

        return seeds

    # ------------------------------------------------------------------
    # Graph traversal
    # ------------------------------------------------------------------

    @staticmethod
    def _bfs(
        graph: nx.DiGraph,
        start: str,
        direction: str,
        depth: int,
    ) -> Set[str]:
        """BFS from *start* up to *depth* hops.

        Args:
            graph:     Dependency graph.
            start:     Seed node.
            direction: 'forward' follows successors (what this file imports);
                       'reverse' follows predecessors (what imports this file).
            depth:     Maximum BFS depth.

        Returns:
            Set of visited nodes (excluding *start*).
        """
        if start not in graph:
            return set()

        visited: Set[str] = set()
        queue = [(start, 0)]

        while queue:
            node, d = queue.pop(0)
            if d >= depth:
                continue
            if direction == "forward":
                neighbours = list(graph.successors(node))
            else:
                neighbours = list(graph.predecessors(node))

            for nb in neighbours:
                if nb not in visited and nb != start:
                    visited.add(nb)
                    queue.append((nb, d + 1))

        return visited

    # ------------------------------------------------------------------
    # Dependency path building
    # ------------------------------------------------------------------

    def _build_dependency_paths(
        self,
        graph: nx.DiGraph,
        seeds: List[str],
        reverse_affected: Set[str],
        max_paths: int,
    ) -> List[DependencyPath]:
        """Build the most informative dependency chains for the output."""
        paths: List[DependencyPath] = []

        for seed in seeds[:max_paths]:
            for target in list(reverse_affected)[:max_paths]:
                try:
                    # Find shortest path from target to seed
                    # (target imports seed, so path goes target→…→seed)
                    chain = nx.shortest_path(graph, source=target, target=seed)
                    if len(chain) >= 2:
                        paths.append(DependencyPath(path=chain))
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    pass
                if len(paths) >= max_paths:
                    break
            if len(paths) >= max_paths:
                break

        # De-duplicate
        seen_chains: Set[str] = set()
        unique: List[DependencyPath] = []
        for dp in paths:
            key = "->".join(dp.path)
            if key not in seen_chains:
                seen_chains.add(key)
                unique.append(dp)

        return unique[:max_paths]

    # ------------------------------------------------------------------
    # Component detection
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_components(file_paths: List[str]) -> List[str]:
        """Map affected file paths to high-level component labels."""
        found: Set[str] = set()
        for fp in file_paths:
            text = fp.lower()
            for pattern, label in _COMPONENT_MAP:
                if pattern.search(text):
                    found.add(label)
        return sorted(found)

    # ------------------------------------------------------------------
    # Risk scoring
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_risk(
        seed_files: List[str],
        indirectly_affected: List[str],
        core_set: Set[str],
        coupling_set: Set[str],
        entry_set: Set[str],
        total_graph_nodes: int,
    ) -> Tuple[str, int]:
        """Return (risk_level, confidence_score)."""
        risk_score = 0

        all_affected = seed_files + indirectly_affected
        total_affected = len(all_affected)

        # Base score from file count
        if total_affected >= _HIGH_RISK_FILE_THRESHOLD:
            risk_score += 3
        elif total_affected >= _MED_RISK_FILE_THRESHOLD:
            risk_score += 1

        # Core module hits
        core_hits = sum(1 for f in all_affected if f in core_set)
        risk_score += core_hits * _CORE_MODULE_HIT_MULTIPLIER

        # High-coupling hits
        coupling_hits = sum(1 for f in all_affected if f in coupling_set)
        risk_score += coupling_hits * _HIGH_COUPLING_HIT_MULTIPLIER

        # Entry-point hit
        if any(f in entry_set for f in all_affected):
            risk_score += 2

        # Map score to level
        if risk_score >= 5:
            risk_level = "high"
        elif risk_score >= 2:
            risk_level = "medium"
        else:
            risk_level = "low"

        # Confidence: higher when more seed files matched and graph is populated
        if total_graph_nodes == 0:
            confidence = 0
        else:
            seed_coverage = min(len(seed_files) / max(total_graph_nodes, 1) * 1000, 1.0)
            base_confidence = 60
            bonus = int(seed_coverage * 30) + (10 if total_affected > 0 else 0)
            confidence = min(base_confidence + bonus, 95)

        return risk_level, confidence
