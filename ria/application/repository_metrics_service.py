"""Repository Metrics application service.

Computes deterministic quantitative software engineering metrics derived from a RepositoryTwin.
Implements :class:`~ria.ports.twin.RepositoryMetricsPort`.
"""

from __future__ import annotations

from typing import Dict

from ria.domain.enums import EdgeKind, NodeKind
from ria.domain.models.repository_metrics import RepositoryMetrics
from ria.domain.models.repository_twin import RepositoryTwin
from ria.ports.twin import RepositoryMetricsPort

__all__ = ["RepositoryMetricsService"]


class RepositoryMetricsService(RepositoryMetricsPort):
    """Service for computing deterministic software metrics."""

    def compute_metrics(self, twin: RepositoryTwin) -> RepositoryMetrics:
        """Compute RepositoryMetrics from a RepositoryTwin."""
        graph = twin.graph_snapshot.graph
        nodes = graph.nodes
        edges = graph.edges

        # Count nodes by kind
        nodes_by_kind: Dict[NodeKind, int] = {}
        for n in nodes:
            nodes_by_kind[n.kind] = nodes_by_kind.get(n.kind, 0) + 1

        # Count edges by kind
        edges_by_kind: Dict[EdgeKind, int] = {}
        for e in edges:
            edges_by_kind[e.kind] = edges_by_kind.get(e.kind, 0) + 1

        files_cnt = nodes_by_kind.get(NodeKind.FILE, 0)
        packages_cnt = nodes_by_kind.get(NodeKind.PACKAGE, 0)
        modules_cnt = nodes_by_kind.get(NodeKind.MODULE, 0)
        classes_cnt = (
            nodes_by_kind.get(NodeKind.CLASS, 0)
            + nodes_by_kind.get(NodeKind.INTERFACE, 0)
            + nodes_by_kind.get(NodeKind.STRUCT, 0)
        )
        functions_cnt = nodes_by_kind.get(NodeKind.FUNCTION, 0)
        methods_cnt = nodes_by_kind.get(NodeKind.METHOD, 0)
        callables_cnt = functions_cnt + methods_cnt

        symbols_cnt = len(nodes)
        references_cnt = edges_by_kind.get(EdgeKind.REFERENCES, 0) + edges_by_kind.get(
            EdgeKind.CALLS, 0
        )
        dependency_cnt = edges_by_kind.get(EdgeKind.IMPORTS, 0) + edges_by_kind.get(
            EdgeKind.USES, 0
        )
        inheritance_cnt = (
            edges_by_kind.get(EdgeKind.EXTENDS, 0)
            + edges_by_kind.get(EdgeKind.IMPLEMENTS, 0)
            + edges_by_kind.get(EdgeKind.OVERRIDES, 0)
        )

        density = len(edges) / max(len(nodes), 1)
        avg_complexity = 1.0 + (len(edges) / max(callables_cnt, 1)) * 0.5

        return RepositoryMetrics(
            repository_size_bytes=sum(len(n.name.encode("utf-8")) for n in nodes),
            files_count=files_cnt,
            packages_count=packages_cnt,
            modules_count=modules_cnt,
            classes_count=classes_cnt,
            functions_count=functions_cnt,
            methods_count=methods_cnt,
            symbols_count=symbols_cnt,
            references_count=references_cnt,
            graph_density=density,
            dependency_count=dependency_cnt,
            inheritance_count=inheritance_cnt,
            cyclomatic_complexity_average=avg_complexity,
        )
