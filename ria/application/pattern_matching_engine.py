"""Pattern Matching Engine application service.

Executes deterministic searches for structural patterns (classes, interfaces, methods,
imports, inheritance chains, decorators, custom expressions) on a RepositoryTwin.
Implements :class:`~ria.ports.query.PatternMatchingPort`.
"""

from __future__ import annotations

from typing import List, Tuple

from ria.domain.enums import EdgeKind, NodeKind
from ria.domain.models.analysis_models import PatternMatch
from ria.domain.models.repository_twin import RepositoryTwin
from ria.ports.query import PatternMatchingPort

__all__ = ["PatternMatchingEngine"]


class PatternMatchingEngine(PatternMatchingPort):
    """Engine for structural pattern matching on a RepositoryTwin."""

    def match_patterns(
        self,
        twin: RepositoryTwin,
        pattern_type: str,
        pattern_expression: str,
    ) -> Tuple[PatternMatch, ...]:
        """Perform structural pattern search on a RepositoryTwin."""
        matches: List[PatternMatch] = []
        graph = twin.graph_snapshot.graph
        expr_lower = pattern_expression.lower()

        if pattern_type in ("class", "interface", "struct", "enum"):
            target_kinds = (
                NodeKind.CLASS,
                NodeKind.INTERFACE,
                NodeKind.STRUCT,
                NodeKind.ENUM,
            )
            for n in graph.nodes:
                if n.kind in target_kinds and (
                    not expr_lower or expr_lower in n.name.lower()
                ):
                    matches.append(
                        PatternMatch(
                            pattern_type=pattern_type,
                            matched_element=n.name,
                            location_path=n.location_path or "",
                        )
                    )
        elif pattern_type in ("method", "function"):
            target_kinds = (NodeKind.FUNCTION, NodeKind.METHOD)
            for n in graph.nodes:
                if n.kind in target_kinds and (
                    not expr_lower or expr_lower in n.name.lower()
                ):
                    matches.append(
                        PatternMatch(
                            pattern_type=pattern_type,
                            matched_element=n.name,
                            location_path=n.location_path or "",
                        )
                    )
        elif pattern_type == "import":
            for e in graph.edges:
                if e.kind is EdgeKind.IMPORTS:
                    src_node = graph.get_node(e.source_id)
                    tgt_node = graph.get_node(e.target_id)
                    if src_node is not None and tgt_node is not None:
                        if not expr_lower or expr_lower in tgt_node.name.lower():
                            matches.append(
                                PatternMatch(
                                    pattern_type="import",
                                    matched_element=f"{src_node.name} imports {tgt_node.name}",
                                    location_path=src_node.location_path or "",
                                )
                            )
        elif pattern_type == "inheritance":
            for e in graph.edges:
                if e.kind in (EdgeKind.EXTENDS, EdgeKind.IMPLEMENTS):
                    src_node = graph.get_node(e.source_id)
                    tgt_node = graph.get_node(e.target_id)
                    if src_node is not None and tgt_node is not None:
                        matches.append(
                            PatternMatch(
                                pattern_type="inheritance",
                                matched_element=f"{src_node.name} -> {tgt_node.name}",
                                location_path=src_node.location_path or "",
                            )
                        )
        else:
            # General fallback search by name
            for n in graph.nodes:
                if not expr_lower or expr_lower in n.name.lower():
                    matches.append(
                        PatternMatch(
                            pattern_type=pattern_type,
                            matched_element=n.name,
                            location_path=n.location_path or "",
                        )
                    )

        return tuple(matches)
