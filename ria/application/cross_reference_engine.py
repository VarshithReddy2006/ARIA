"""Cross Reference Engine application service.

Computes cross-reference links (Who Calls, Who References, Who Imports, Who Extends,
Who Implements, Who Uses, Incoming, Outgoing) for symbols on a RepositoryTwin.
Implements :class:`~ria.ports.query.CrossReferencePort`.
"""

from __future__ import annotations

from typing import List, Tuple

from ria.domain.models.analysis_models import CrossReference
from ria.domain.models.repository_twin import RepositoryTwin
from ria.ports.query import CrossReferencePort

__all__ = ["CrossReferenceEngine"]


class CrossReferenceEngine(CrossReferencePort):
    """Engine for computing cross-reference links across codebase."""

    def get_cross_references(
        self,
        twin: RepositoryTwin,
        symbol_name: str,
    ) -> Tuple[CrossReference, ...]:
        """Look up cross-references for symbol_name."""
        matches: List[CrossReference] = []
        graph = twin.graph_snapshot.graph
        sym_lower = symbol_name.lower()

        for e in graph.edges:
            src_node = graph.get_node(e.source_id)
            tgt_node = graph.get_node(e.target_id)
            if src_node is not None and tgt_node is not None:
                if (
                    sym_lower in src_node.name.lower()
                    or sym_lower in tgt_node.name.lower()
                ):
                    matches.append(
                        CrossReference(
                            source_symbol=src_node.name,
                            target_symbol=tgt_node.name,
                            relation_kind=e.kind.value,
                            source_file=src_node.location_path or "",
                            target_file=tgt_node.location_path or "",
                        )
                    )

        return tuple(matches)
