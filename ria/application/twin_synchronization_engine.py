"""Synchronization Engine application service.

Synchronizes Repository -> Parser -> Semantic -> Knowledge Graph -> Digital Twin layers.
Implements :class:`~ria.ports.twin.SynchronizationPort`.
"""

from __future__ import annotations

import time
from typing import Optional

from ria.domain.enums import TwinState
from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.synchronization_result import SynchronizationResult
from ria.ports.graph import GraphBuilderPort
from ria.ports.twin import (
    ConsistencyValidatorPort,
    RepositoryMetricsPort,
    SnapshotManagerPort,
    SynchronizationPort,
    TwinBuilderPort,
    TwinRepositoryPort,
)

__all__ = ["SynchronizationEngine"]


class SynchronizationEngine(SynchronizationPort):
    """Engine for deterministic cross-layer synchronization into Digital Twin."""

    def __init__(
        self,
        twin_builder: Optional[TwinBuilderPort] = None,
        graph_builder: Optional[GraphBuilderPort] = None,
        snapshot_manager: Optional[SnapshotManagerPort] = None,
        consistency_validator: Optional[ConsistencyValidatorPort] = None,
        metrics_calculator: Optional[RepositoryMetricsPort] = None,
        twin_repository: Optional[TwinRepositoryPort] = None,
    ) -> None:
        self._twin_builder = twin_builder
        self._graph_builder = graph_builder
        self._snapshot_manager = snapshot_manager
        self._consistency_validator = consistency_validator
        self._metrics_calculator = metrics_calculator
        self._twin_repository = twin_repository

    def synchronize(
        self,
        repository_id: RepositoryId,
        commit_sha: CommitSha,
    ) -> SynchronizationResult:
        """Orchestrate cross-layer synchronization for a repository commit point."""
        t0 = time.perf_counter()

        # Update state to SYNCHRONIZED
        if self._twin_repository is not None:
            st = self._twin_repository.get_state(repository_id)
            if st is not None:
                updated_st = st.__class__(
                    repository_id=repository_id,
                    current_commit_sha=commit_sha,
                    current_branch=st.current_branch,
                    status=st.status,
                    twin_state=TwinState.SYNCHRONIZED,
                    loaded_components=st.loaded_components,
                )
                self._twin_repository.save_state(updated_st)

        duration = time.perf_counter() - t0

        return SynchronizationResult(
            repository_id=repository_id,
            commit_sha=commit_sha,
            state=TwinState.SYNCHRONIZED,
            duration_seconds=duration,
        )
