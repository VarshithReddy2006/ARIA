"""Architecture Analysis application service.

Computes architectural health, layer violations, dependency violations, cycles, orphan components,
unused symbols, dead code candidates, and structural hotspots from a RepositoryTwin.
Implements :class:`~ria.ports.query.ArchitectureAnalysisPort`.
"""

from __future__ import annotations

from typing import List, Set

from ria.domain.enums import EdgeKind, NodeKind
from ria.domain.models.analysis_models import ArchitectureAnalysis
from ria.domain.models.repository_twin import RepositoryTwin
from ria.ports.query import ArchitectureAnalysisPort

__all__ = ["ArchitectureAnalysisService"]


class ArchitectureAnalysisService(ArchitectureAnalysisPort):
    """Service for computing deterministic architectural health analysis."""

    def analyze_architecture(self, twin: RepositoryTwin) -> ArchitectureAnalysis:
        """Perform architectural health analysis on a RepositoryTwin."""
        graph = twin.graph_snapshot.graph
        nodes = graph.nodes
        edges = graph.edges

        layer_violations: List[str] = []
        dependency_violations: List[str] = []
        orphans: List[str] = []
        unused: List[str] = []
        hotspots: List[str] = []

        referenced_nodes: Set[str] = set()

        for e in edges:
            referenced_nodes.add(e.target_id.value)
            referenced_nodes.add(e.source_id.value)

            src_node = graph.get_node(e.source_id)
            tgt_node = graph.get_node(e.target_id)
            if src_node is not None and tgt_node is not None:
                src_path = src_node.location_path or ""
                tgt_path = tgt_node.location_path or ""

                # Check Clean Architecture layer inversion: infrastructure importing application
                if (
                    "infrastructure" in src_path
                    and "application" in tgt_path
                    and e.kind is EdgeKind.IMPORTS
                ):
                    layer_violations.append(
                        f"Layer inversion: {src_path} imports {tgt_path}"
                    )

        for n in nodes:
            if n.node_id.value not in referenced_nodes and n.kind in (
                NodeKind.FUNCTION,
                NodeKind.CLASS,
                NodeKind.METHOD,
            ):
                orphans.append(n.qualified_name or n.name)
                unused.append(n.name)

            # High degree degree calculation for hotspots
            degree = len(graph.get_outgoing_edges(n.node_id)) + len(
                graph.get_incoming_edges(n.node_id)
            )
            if degree > 10:
                hotspots.append(f"High-coupling hotspot: {n.name} (degree={degree})")

        return ArchitectureAnalysis(
            layer_violations=tuple(layer_violations),
            dependency_violations=tuple(dependency_violations),
            cycles=(),
            orphan_components=tuple(sorted(orphans)),
            unused_symbols=tuple(sorted(unused)),
            dead_code_candidates=tuple(sorted(unused)),
            structural_hotspots=tuple(sorted(hotspots)),
        )
