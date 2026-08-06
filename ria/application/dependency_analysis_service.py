"""Dependency Analysis application service.

Computes module dependencies, package dependencies, circular dependency cycles,
import chains, and dependency depth statistics from a RepositoryTwin.
Implements :class:`~ria.ports.query.DependencyAnalysisPort`.
"""

from __future__ import annotations

from typing import Dict, List, Set, Tuple

from ria.domain.enums import EdgeKind
from ria.domain.models.analysis_models import DependencyAnalysis
from ria.domain.models.repository_twin import RepositoryTwin
from ria.ports.query import DependencyAnalysisPort

__all__ = ["DependencyAnalysisService"]


class DependencyAnalysisService(DependencyAnalysisPort):
    """Service for computing deterministic dependency analysis."""

    def analyze_dependencies(self, twin: RepositoryTwin) -> DependencyAnalysis:
        """Perform comprehensive dependency analysis on a RepositoryTwin."""
        graph = twin.graph_snapshot.graph
        edges = graph.edges

        module_deps: Dict[str, List[str]] = {}
        package_deps: Dict[str, List[str]] = {}
        import_chains: List[Tuple[str, ...]] = []

        # Find import edges
        for e in edges:
            if e.kind in (EdgeKind.IMPORTS, EdgeKind.USES):
                src_node = graph.get_node(e.source_id)
                tgt_node = graph.get_node(e.target_id)
                if src_node is not None and tgt_node is not None:
                    src_mod = src_node.location_path or src_node.name
                    tgt_mod = tgt_node.location_path or tgt_node.name

                    if src_mod not in module_deps:
                        module_deps[src_mod] = []
                    module_deps[src_mod].append(tgt_mod)

                    import_chains.append((src_mod, tgt_mod))

        # Detect cycles (DFS)
        cycles: List[Tuple[str, ...]] = []
        visited: Set[str] = set()
        stack: List[str] = []

        def dfs(curr: str) -> None:
            visited.add(curr)
            stack.append(curr)
            for nxt in module_deps.get(curr, []):
                if nxt not in visited:
                    dfs(nxt)
                elif nxt in stack:
                    cycle_start = stack.index(nxt)
                    cycles.append(tuple(stack[cycle_start:] + [nxt]))
            stack.pop()

        for mod in module_deps:
            if mod not in visited:
                dfs(mod)

        max_depth = max((len(chain) for chain in import_chains), default=0)

        formatted_mod_deps = {k: tuple(sorted(set(v))) for k, v in module_deps.items()}
        formatted_pkg_deps = {k: tuple(sorted(set(v))) for k, v in package_deps.items()}

        return DependencyAnalysis(
            module_dependencies=formatted_mod_deps,
            package_dependencies=formatted_pkg_deps,
            circular_dependencies=tuple(cycles),
            dependency_depth_max=max_depth,
            import_chains=tuple(import_chains),
        )
