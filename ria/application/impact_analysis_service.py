"""Impact Analysis application service.

Computes deterministic change impact analysis (affected files, symbols, classes, functions,
dependency ripple, inheritance ripple, reference ripple) for modified target files.
Implements :class:`~ria.ports.query.ImpactAnalysisPort`.
"""

from __future__ import annotations

from typing import Set, Tuple

from ria.domain.enums import EdgeKind, NodeKind
from ria.domain.models.analysis_models import ImpactAnalysis
from ria.domain.models.repository_twin import RepositoryTwin
from ria.ports.query import ImpactAnalysisPort

__all__ = ["ImpactAnalysisService"]


class ImpactAnalysisService(ImpactAnalysisPort):
    """Service for computing deterministic change impact analysis."""

    def analyze_impact(
        self,
        twin: RepositoryTwin,
        changed_files: Tuple[str, ...],
    ) -> ImpactAnalysis:
        """Perform change impact analysis for changed target files on a RepositoryTwin."""
        graph = twin.graph_snapshot.graph
        changed_set = set(changed_files)

        affected_files: Set[str] = set(changed_files)
        affected_symbols: Set[str] = set()
        affected_classes: Set[str] = set()
        affected_functions: Set[str] = set()

        dep_ripple = 0
        inh_ripple = 0
        ref_ripple = 0

        # Trace outgoing and incoming edges for nodes in changed files
        for e in graph.edges:
            src_node = graph.get_node(e.source_id)
            tgt_node = graph.get_node(e.target_id)
            if src_node is not None and tgt_node is not None:
                src_path = src_node.location_path or ""
                tgt_path = tgt_node.location_path or ""

                if src_path in changed_set or tgt_path in changed_set:
                    if e.kind in (EdgeKind.IMPORTS, EdgeKind.USES):
                        dep_ripple += 1
                    elif e.kind in (
                        EdgeKind.EXTENDS,
                        EdgeKind.IMPLEMENTS,
                        EdgeKind.OVERRIDES,
                    ):
                        inh_ripple += 1
                    elif e.kind in (EdgeKind.REFERENCES, EdgeKind.CALLS):
                        ref_ripple += 1

                    if src_path:
                        affected_files.add(src_path)
                    if tgt_path:
                        affected_files.add(tgt_path)

                    if tgt_node.name:
                        affected_symbols.add(tgt_node.name)
                        if tgt_node.kind in (
                            NodeKind.CLASS,
                            NodeKind.INTERFACE,
                            NodeKind.STRUCT,
                        ):
                            affected_classes.add(tgt_node.name)
                        elif tgt_node.kind in (NodeKind.FUNCTION, NodeKind.METHOD):
                            affected_functions.add(tgt_node.name)

        return ImpactAnalysis(
            target_files=changed_files,
            affected_files=tuple(sorted(affected_files)),
            affected_symbols=tuple(sorted(affected_symbols)),
            affected_classes=tuple(sorted(affected_classes)),
            affected_functions=tuple(sorted(affected_functions)),
            dependency_ripple_count=dep_ripple,
            inheritance_ripple_count=inh_ripple,
            reference_ripple_count=ref_ripple,
        )
