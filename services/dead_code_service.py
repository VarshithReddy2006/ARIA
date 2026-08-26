import fnmatch
import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

import networkx as nx

from models.dead_code import (
    DeadCodeResult,
    DeadFile,
    OrphanModule,
    DeadDependencyChain,
)
from services.github_service import GitHubService
from services.graph_service import GraphService
from services.architecture_service import ArchitectureService
from core.repository_context import RepositoryContext

logger = logging.getLogger(__name__)


class DeadCodeService:
    """Orchestrates Dead Code Intelligence (PH2-005A)."""

    def __init__(
        self,
        github_service: Optional[GitHubService] = None,
        graph_service: Optional[GraphService] = None,
        architecture_service: Optional[ArchitectureService] = None,
        scores_file_path: Optional[str] = None,
    ) -> None:
        self.github_service = github_service or GitHubService()
        self.graph_service = graph_service or GraphService()
        self.architecture_service = architecture_service or ArchitectureService()

        if scores_file_path is None:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.scores_file_path = os.path.join(
                project_root, "data", "dead_code_scores.json"
            )
        else:
            self.scores_file_path = scores_file_path

        self.default_ignores = [
            "migrations/",
            "examples/",
            "playground/",
            "templates/",
            "legacy/",
            "**pycache__/",
            "dist/",
            "build/",
        ]

    def is_ignored(self, file_path: str, patterns: List[str]) -> bool:
        """Determines if a file path matches any of the ignore patterns (case-insensitive)."""
        norm_path = file_path.replace("\\", "/").lower()
        for pat in patterns:
            pat_clean = pat.replace("\\", "/").lower()

            # Directory pattern (e.g. migrations/)
            if pat_clean.endswith("/"):
                dir_name = pat_clean[:-1]
                parts = norm_path.split("/")
                if dir_name in parts:
                    return True

            # Standard glob matching
            if fnmatch.fnmatch(norm_path, pat_clean) or fnmatch.fnmatch(
                os.path.basename(norm_path), pat_clean
            ):
                return True
        return False

    def load_ignore_patterns(self) -> List[str]:
        """Loads default patterns and appends customization from data/dead_code_ignore.json."""
        patterns = list(self.default_ignores)
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ignore_file = os.path.join(project_root, "data", "dead_code_ignore.json")

        if os.path.exists(ignore_file):
            try:
                with open(ignore_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                    if isinstance(data, list):
                        patterns.extend(data)
            except Exception as exc:
                logger.warning("Failed to load dead_code_ignore.json: %s", exc)
        return patterns

    def _find_last_reachable_parent(
        self, graph: nx.DiGraph, orphan: str, reachable_nodes: Set[str]
    ) -> Optional[str]:
        """Finds the closest reachable node connected to the orphan in the undirected graph."""
        if not reachable_nodes:
            return None

        ug = graph.to_undirected()
        if orphan not in ug:
            return None

        best_node = None
        min_dist = float("inf")

        for r_node in reachable_nodes:
            if r_node in ug:
                try:
                    if nx.has_path(ug, orphan, r_node):
                        dist = nx.shortest_path_length(ug, orphan, r_node)
                        if dist < min_dist:
                            min_dist = dist
                            best_node = r_node
                except Exception:
                    pass

        return best_node

    def _find_dead_chains(
        self, unreachable_subgraph: nx.DiGraph, centrality: Dict[str, float]
    ) -> List[DeadDependencyChain]:
        """Finds weakly connected components in the unreachable graph and extracts path chains."""
        chains = []
        H = unreachable_subgraph

        components = list(nx.weakly_connected_components(H))
        for comp in components:
            comp_sub = H.subgraph(comp)
            comp_nodes = list(comp)

            if len(comp_nodes) < 2:
                continue

            roots = [n for n in comp_nodes if comp_sub.in_degree(n) == 0]
            if not roots:
                roots = [comp_nodes[0]]

            all_paths = []
            visited = set()

            def dfs_paths(node, current_path):
                visited.add(node)
                current_path.append(node)
                successors = [s for s in comp_sub.successors(node) if s not in visited]
                if not successors:
                    if len(current_path) >= 2:
                        all_paths.append(list(current_path))
                else:
                    for s in successors:
                        dfs_paths(s, list(current_path))
                visited.remove(node)

            for r in roots:
                dfs_paths(r, [])

            if not all_paths:
                continue

            # Sort paths by length descending
            all_paths.sort(key=len, reverse=True)

            # De-duplicate sub-paths
            filtered_paths = []
            for p in all_paths:
                is_subpath = False
                for fp in filtered_paths:
                    for i in range(len(fp) - len(p) + 1):
                        if fp[i : i + len(p)] == p:
                            is_subpath = True
                            break
                    if is_subpath:
                        break
                if not is_subpath:
                    filtered_paths.append(p)

            for path in filtered_paths:
                length = len(path) - 1
                total_nodes = len(path)
                max_cent = max(centrality.get(n, 0.0) for n in path)

                chain_rep = " -> ".join(os.path.basename(n) for n in path)
                recommendation = f"Dependency chain [{chain_rep}] appears unreachable and may be removable as a unit."

                chains.append(
                    DeadDependencyChain(
                        chain=path,
                        confidence=0.95,
                        risk_level="SAFE",
                        recommendation=recommendation,
                        length=length,
                        total_nodes=total_nodes,
                        max_centrality=round(max_cent, 4),
                    )
                )

        return chains

    def _load_previous_score(self, repo_fullName: str) -> Optional[int]:
        if os.path.exists(self.scores_file_path):
            try:
                with open(self.scores_file_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                    if isinstance(data, dict) and repo_fullName in data:
                        return data[repo_fullName].get("score")
            except Exception as exc:
                logger.warning("Failed to load previous score: %s", exc)
        return None

    def _save_new_score(self, repo_fullName: str, score: int) -> None:
        data = {}
        os.makedirs(os.path.dirname(self.scores_file_path), exist_ok=True)
        if os.path.exists(self.scores_file_path):
            try:
                with open(self.scores_file_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except Exception:
                pass

        data[repo_fullName] = {
            "score": score,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            with open(self.scores_file_path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
        except Exception as exc:
            logger.warning("Failed to save score to %s: %s", self.scores_file_path, exc)

    def analyze(self, repo_name: str) -> DeadCodeResult:
        """Wrapper method for compatibility with ReportComposer and test mocks."""
        owner, repo = repo_name.split("/", 1)
        return self.analyze_dead_code(owner, repo)

    def analyze_dead_code(
        self,
        owner: str,
        repo: str,
        context: Optional[RepositoryContext] = None,
    ) -> DeadCodeResult:
        """Orchestrates reachability dead code calculations."""
        repo_fullName = f"{owner}/{repo}"

        if context is None:
            context = RepositoryContext(repo_fullName)

        if not self.graph_service.graph_exists(repo_fullName):
            raise ValueError(
                f"No dependency graph found for '{repo_fullName}'. "
                "Run repository architecture build first."
            )

        summary = self.architecture_service.get_summary(repo_fullName)
        if not summary:
            try:
                from storage.snapshot_store import JsonSnapshotStore

                store = JsonSnapshotStore()
                snap = store.load(repo_fullName)
                if snap:
                    summary = snap.get("architecture")
            except Exception:
                pass

        if not summary:
            raise ValueError(
                f"No architecture summary found for '{repo_fullName}'. "
                "Run repository architecture build first."
            )

        G = context.dependency_graph
        if G is None:
            G = self.graph_service.load_graph(repo_fullName)
        if G is None:
            G = nx.DiGraph()

        ignore_patterns = self.load_ignore_patterns()

        # Find entry points
        raw_entry_points = getattr(summary, "entry_points", None)
        if raw_entry_points is None and isinstance(summary, dict):
            raw_entry_points = summary.get("entry_points")
        entry_points = set(raw_entry_points or [])
        for node in G.nodes:
            basename = os.path.basename(node).lower()
            if basename in {
                "main.py",
                "__main__.py",
                "app.py",
                "application.py",
                "server.py",
                "index.js",
                "server.js",
                "app.js",
                "main.tsx",
                "app.tsx",
                "api.py",
                "run.py",
                "manage.py",
                "wsgi.py",
                "asgi.py",
            }:
                entry_points.add(node)

        # Reachability calculations
        reachable_nodes = set()
        for ep in entry_points:
            if ep in G:
                reachable_nodes.add(ep)
                reachable_nodes.update(nx.descendants(G, ep))

        all_unreachable = set(G.nodes) - reachable_nodes

        unreachable_filtered = {
            node
            for node in all_unreachable
            if not self.is_ignored(node, ignore_patterns)
        }
        reachable_filtered = {
            node
            for node in reachable_nodes
            if not self.is_ignored(node, ignore_patterns)
        }

        H = G.subgraph(unreachable_filtered)

        centrality = {}
        if G.number_of_nodes() > 1:
            centrality = nx.degree_centrality(G)
        else:
            centrality = {n: 0.0 for n in G.nodes}

        unused_files_list = []
        orphan_modules_list = []
        total_deductions = 0.0

        for v in unreachable_filtered:
            cent_val = centrality.get(v, 0.0)
            out_deg = G.out_degree(v)
            subtree_size = len(nx.descendants(H, v))

            # Graph-weighted score: factors in centrality, out degree, and subtree size
            node_weight = 1.0 + 10.0 * cent_val + 0.5 * out_deg + 1.0 * subtree_size

            in_deg = G.in_degree(v)
            if in_deg == 0:
                base_factor = 6.0
                total_deductions += base_factor * node_weight

                unused_files_list.append(
                    DeadFile(
                        file_path=v,
                        confidence=0.95,
                        risk_level="SAFE",
                        recommendation=f"Consider removing unused file {v}",
                    )
                )
            else:
                base_factor = 4.0
                total_deductions += base_factor * node_weight

                last_parent = self._find_last_reachable_parent(G, v, reachable_filtered)

                rec = (
                    f"Review orphaned module {v}; no active execution path reaches it."
                )
                orphan_modules_list.append(
                    OrphanModule(
                        file_path=v,
                        confidence=0.90,
                        risk_level="REVIEW",
                        recommendation=rec,
                        last_reachable_parent=last_parent,
                    )
                )

        chains = self._find_dead_chains(H, centrality)
        for c in chains:
            total_deductions += 3.0 * len(c.chain)

        cleanup_score = max(0, min(100, 100 - int(total_deductions)))

        total_findings_count = (
            len(unused_files_list) + len(orphan_modules_list) + len(chains)
        )
        if total_findings_count <= 2:
            effort = "LOW"
        elif total_findings_count <= 10:
            effort = "MEDIUM"
        else:
            effort = "HIGH"

        # Generate recommendations sorted by impact
        recommendations_with_weights = []
        for f in unused_files_list:
            cent = centrality.get(f.file_path, 0.0)
            od = G.out_degree(f.file_path)
            st = len(nx.descendants(H, f.file_path))
            w = 6.0 * (1.0 + 10.0 * cent + 0.5 * od + 1.0 * st)

            if st > 0:
                msg = f"Remove unused subtree starting at {f.file_path} (cascades to {st} dead modules)."
            else:
                msg = f"Remove unused file {f.file_path} (no active imports)."
            recommendations_with_weights.append((msg, w))

        for o in orphan_modules_list:
            cent = centrality.get(o.file_path, 0.0)
            od = G.out_degree(o.file_path)
            st = len(nx.descendants(H, o.file_path))
            w = 4.0 * (1.0 + 10.0 * cent + 0.5 * od + 1.0 * st)

            if o.last_reachable_parent:
                msg = f"Review orphaned module {o.file_path} (previously connected via {o.last_reachable_parent})."
            else:
                msg = f"Review orphaned module {o.file_path} (completely isolated from active graph)."
            recommendations_with_weights.append((msg, w))

        for c in chains:
            w = 3.0 * len(c.chain)
            chain_rep = " -> ".join(os.path.basename(n) for n in c.chain)
            msg = f"Delete unreachable dependency chain: {chain_rep} (removes {len(c.chain)} dead files)."
            recommendations_with_weights.append((msg, w))

        recommendations_with_weights.sort(key=lambda x: x[1], reverse=True)
        cleanup_recommendations = [r[0] for r in recommendations_with_weights[:10]]

        prev_score = self._load_previous_score(repo_fullName)
        self._save_new_score(repo_fullName, cleanup_score)

        return DeadCodeResult(
            repo=repo_fullName,
            cleanup_score=cleanup_score,
            previous_cleanup_score=prev_score,
            estimated_cleanup_effort=effort,
            unused_files=unused_files_list,
            orphan_modules=orphan_modules_list,
            dead_dependency_chains=chains,
            cleanup_recommendations=cleanup_recommendations,
            analyzed_at=datetime.now(timezone.utc).isoformat(),
        )
