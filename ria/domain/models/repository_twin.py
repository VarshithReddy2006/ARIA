"""RepositoryTwin domain entity.

Canonical runtime Digital Twin model unifying repository identity, state, knowledge graph snapshot, metrics, and metadata.
"""

from __future__ import annotations

from dataclasses import dataclass

from ria.domain.models.graph_snapshot import GraphSnapshot
from ria.domain.models.repository import Repository
from ria.domain.models.repository_metrics import RepositoryMetrics
from ria.domain.models.repository_state import RepositoryState
from ria.domain.models.twin_id import TwinId
from ria.domain.models.twin_result import TwinMetadata, TwinStatistics

__all__ = ["RepositoryTwin"]


@dataclass(frozen=True)
class RepositoryTwin:
    """Canonical runtime representation of a Repository Digital Twin.

    Attributes:
        twin_id: Unique TwinId.
        repository: Aggregate Repository entity.
        state: Active RepositoryState entity.
        graph_snapshot: Bound GraphSnapshot instance.
        metrics: Derived RepositoryMetrics instance.
        metadata: Provenance TwinMetadata instance.
        statistics: Summary TwinStatistics instance.
    """

    twin_id: TwinId
    repository: Repository
    state: RepositoryState
    graph_snapshot: GraphSnapshot
    metrics: RepositoryMetrics
    metadata: TwinMetadata
    statistics: TwinStatistics
