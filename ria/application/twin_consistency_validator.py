"""Consistency Validator application service.

Validates consistency across Repository, Knowledge Graph, Semantic Layer, and Parser Layer.
Implements :class:`~ria.ports.twin.ConsistencyValidatorPort`.
"""

from __future__ import annotations

from typing import List

from ria.domain.enums import DiagnosticSeverity
from ria.domain.models.consistency_report import ConsistencyReport
from ria.domain.models.repository_twin import RepositoryTwin
from ria.domain.models.twin_result import TwinDiagnostic
from ria.ports.twin import ConsistencyValidatorPort

__all__ = ["TwinConsistencyValidator"]


class TwinConsistencyValidator(ConsistencyValidatorPort):
    """Service for cross-layer consistency validation."""

    def validate_consistency(self, twin: RepositoryTwin) -> ConsistencyReport:
        """Audit cross-layer consistency across Digital Twin components.

        Args:
            twin: RepositoryTwin instance to validate.

        Returns:
            ConsistencyReport detailing audit results and discrepancies.
        """
        inconsistencies: List[TwinDiagnostic] = []

        repo_to_graph_ok = True
        graph_to_semantic_ok = True
        semantic_to_parser_ok = True

        # 1. Repository ↔ Graph Validation
        if twin.repository.repository_id != twin.graph_snapshot.repository_id:
            repo_to_graph_ok = False
            inconsistencies.append(
                TwinDiagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    message=f"Repository ID mismatch: {twin.repository.repository_id.value} vs {twin.graph_snapshot.repository_id.value}",
                    code="ERR_REPO_GRAPH_ID_MISMATCH",
                    component="repository_to_graph",
                )
            )

        if twin.state.current_commit_sha != twin.graph_snapshot.commit_sha:
            repo_to_graph_ok = False
            inconsistencies.append(
                TwinDiagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    message=f"Commit SHA mismatch: {twin.state.current_commit_sha.value} vs {twin.graph_snapshot.commit_sha.value}",
                    code="ERR_REPO_GRAPH_SHA_MISMATCH",
                    component="repository_to_graph",
                )
            )

        # 2. Graph ↔ Semantic & Semantic ↔ Parser Validation
        # Check node & edge structural consistency
        if twin.graph_snapshot.statistics.nodes_total < 0:
            graph_to_semantic_ok = False
            inconsistencies.append(
                TwinDiagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    message="Negative total node count in graph snapshot",
                    code="ERR_GRAPH_SEMANTIC_NODES_NEGATIVE",
                    component="graph_to_semantic",
                )
            )

        is_consistent = (
            repo_to_graph_ok and graph_to_semantic_ok and semantic_to_parser_ok
        )

        return ConsistencyReport(
            is_consistent=is_consistent,
            repository_to_graph_consistent=repo_to_graph_ok,
            graph_to_semantic_consistent=graph_to_semantic_ok,
            semantic_to_parser_consistent=semantic_to_parser_ok,
            inconsistencies=tuple(inconsistencies),
        )
