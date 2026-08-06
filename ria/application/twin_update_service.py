"""Twin Update application service.

Performs incremental Digital Twin updates derived from ChangeSets.
"""

from __future__ import annotations

from typing import Optional

from ria.domain.identity import CommitSha
from ria.domain.models.change_set import ChangeSet
from ria.domain.models.graph_snapshot import GraphSnapshot
from ria.domain.models.repository_twin import RepositoryTwin
from ria.ports.graph import GraphBuilderPort
from ria.ports.twin import TwinBuilderPort

__all__ = ["TwinUpdateService"]


class TwinUpdateService:
    """Service for incremental digital twin updates."""

    def __init__(
        self,
        twin_builder: Optional[TwinBuilderPort] = None,
        graph_builder: Optional[GraphBuilderPort] = None,
    ) -> None:
        self._twin_builder = twin_builder
        self._graph_builder = graph_builder

    def update_twin(
        self,
        previous_twin: RepositoryTwin,
        change_set: ChangeSet,
        updated_graph_snapshot: GraphSnapshot,
    ) -> RepositoryTwin:
        """Apply ChangeSet incrementally to construct updated RepositoryTwin."""
        if self._twin_builder is not None:
            return self._twin_builder.update_twin(
                previous_twin=previous_twin,
                change_set=change_set,
                updated_graph_snapshot=updated_graph_snapshot,
            )

        # Fallback inline reconstruction with updated commit SHA and graph snapshot
        head_commit = CommitSha(change_set.head_sha)
        new_state = previous_twin.state.__class__(
            repository_id=previous_twin.repository.repository_id,
            current_commit_sha=head_commit,
            current_branch=previous_twin.state.current_branch,
            status=previous_twin.state.status,
            twin_state=previous_twin.state.twin_state,
            loaded_components=previous_twin.state.loaded_components,
        )

        return RepositoryTwin(
            twin_id=previous_twin.twin_id,
            repository=previous_twin.repository,
            state=new_state,
            graph_snapshot=updated_graph_snapshot,
            metrics=previous_twin.metrics,
            metadata=previous_twin.metadata,
            statistics=previous_twin.statistics,
        )
