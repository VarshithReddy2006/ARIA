"""Twin Builder application service.

Constructs complete RepositoryTwin entities from Repository aggregates and GraphSnapshots.
Implements :class:`~ria.ports.twin.TwinBuilderPort`.
"""

from __future__ import annotations

from typing import Dict

from ria.domain.enums import NodeKind, TwinState
from ria.domain.identity import CommitSha
from ria.domain.models.change_set import ChangeSet
from ria.domain.models.graph_snapshot import GraphSnapshot
from ria.domain.models.repository import Repository
from ria.domain.models.repository_metrics import RepositoryMetrics
from ria.domain.models.repository_state import RepositoryState
from ria.domain.models.repository_twin import RepositoryTwin
from ria.domain.models.twin_id import TwinId
from ria.domain.models.twin_result import TwinMetadata, TwinStatistics
from ria.ports.twin import TwinBuilderPort

__all__ = ["TwinBuilderService"]


class TwinBuilderService(TwinBuilderPort):
    """Service for constructing RepositoryTwin entities."""

    def __init__(
        self, builder_version: str = "1.0.0", schema_version: str = "1.0.0"
    ) -> None:
        self._builder_version = builder_version
        self._schema_version = schema_version

    def build_twin(
        self,
        repository: Repository,
        commit_sha: CommitSha,
        graph_snapshot: GraphSnapshot,
    ) -> RepositoryTwin:
        """Construct a complete RepositoryTwin instance.

        Args:
            repository: Repository aggregate root.
            commit_sha: Bound commit SHA snapshot point.
            graph_snapshot: Knowledge Graph snapshot.

        Returns:
            Complete RepositoryTwin instance.
        """
        tid = TwinId.for_repository(repository.repository_id)
        state = RepositoryState(
            repository_id=repository.repository_id,
            current_commit_sha=commit_sha,
            status=repository.status,
            twin_state=TwinState.SYNCHRONIZED,
            loaded_components=("repository", "parser", "semantic", "graph"),
        )

        # Count nodes by kind in graph
        nodes_by_kind: Dict[NodeKind, int] = {}
        for n in graph_snapshot.graph.nodes:
            nodes_by_kind[n.kind] = nodes_by_kind.get(n.kind, 0) + 1

        files_cnt = nodes_by_kind.get(NodeKind.FILE, 0) + nodes_by_kind.get(
            NodeKind.MODULE, 0
        )
        packages_cnt = nodes_by_kind.get(NodeKind.PACKAGE, 0)
        classes_cnt = nodes_by_kind.get(NodeKind.CLASS, 0)
        functions_cnt = nodes_by_kind.get(NodeKind.FUNCTION, 0)
        methods_cnt = nodes_by_kind.get(NodeKind.METHOD, 0)

        metrics = RepositoryMetrics(
            files_count=files_cnt,
            packages_count=packages_cnt,
            modules_count=nodes_by_kind.get(NodeKind.MODULE, 0),
            classes_count=classes_cnt,
            functions_count=functions_cnt,
            methods_count=methods_cnt,
            symbols_count=len(graph_snapshot.graph.nodes),
            references_count=len(graph_snapshot.graph.edges),
            graph_density=len(graph_snapshot.graph.edges)
            / max(len(graph_snapshot.graph.nodes), 1),
        )

        metadata = TwinMetadata(
            repository_id=repository.repository_id.value,
            commit_sha=commit_sha.value,
            builder_version=self._builder_version,
            schema_version=self._schema_version,
        )

        statistics = TwinStatistics(
            files_total=files_cnt,
            modules_total=nodes_by_kind.get(NodeKind.MODULE, 0),
            symbols_total=len(graph_snapshot.graph.nodes),
            nodes_total=graph_snapshot.statistics.nodes_total,
            edges_total=graph_snapshot.statistics.edges_total,
        )

        return RepositoryTwin(
            twin_id=tid,
            repository=repository,
            state=state,
            graph_snapshot=graph_snapshot,
            metrics=metrics,
            metadata=metadata,
            statistics=statistics,
        )

    def update_twin(
        self,
        previous_twin: RepositoryTwin,
        change_set: ChangeSet,
        updated_graph_snapshot: GraphSnapshot,
    ) -> RepositoryTwin:
        """Incrementally update a RepositoryTwin."""
        return self.build_twin(
            repository=previous_twin.repository,
            commit_sha=CommitSha(change_set.head_sha),
            graph_snapshot=updated_graph_snapshot,
        )
