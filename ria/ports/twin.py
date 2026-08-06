"""Port protocols for Milestone 6 — Repository Digital Twin.

Defines runtime checkable protocols for twin construction, state management, snapshot management,
synchronization, consistency validation, metrics computation, registry, caching, and persistence.
"""

from __future__ import annotations

from typing import FrozenSet, Optional, Protocol, runtime_checkable

from ria.domain.enums import TwinState
from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.change_set import ChangeSet
from ria.domain.models.consistency_report import ConsistencyReport
from ria.domain.models.graph_snapshot import GraphSnapshot
from ria.domain.models.parser_identity import ComponentVersion
from ria.domain.models.repository import Repository
from ria.domain.models.repository_metrics import RepositoryMetrics
from ria.domain.models.repository_state import RepositoryState
from ria.domain.models.repository_twin import RepositoryTwin
from ria.domain.models.synchronization_result import SynchronizationResult
from ria.domain.models.twin_identity import TwinCacheKey
from ria.domain.models.twin_snapshot import TwinSnapshot

__all__ = [
    "TwinBuilderPort",
    "TwinRepositoryPort",
    "TwinStorePort",
    "TwinCacheStore",
    "TwinRegistryPort",
    "SnapshotManagerPort",
    "SynchronizationPort",
    "ConsistencyValidatorPort",
    "RepositoryMetricsPort",
    "TwinLifecyclePort",
]


@runtime_checkable
class TwinBuilderPort(Protocol):
    """Port for building complete RepositoryTwin instances."""

    def build_twin(
        self,
        repository: Repository,
        commit_sha: CommitSha,
        graph_snapshot: GraphSnapshot,
    ) -> RepositoryTwin:
        """Construct a complete RepositoryTwin."""
        ...

    def update_twin(
        self,
        previous_twin: RepositoryTwin,
        change_set: ChangeSet,
        updated_graph_snapshot: GraphSnapshot,
    ) -> RepositoryTwin:
        """Incrementally update a RepositoryTwin."""
        ...


@runtime_checkable
class TwinRepositoryPort(Protocol):
    """Port for persistence of RepositoryState entities."""

    def get_state(self, repository_id: RepositoryId) -> Optional[RepositoryState]:
        """Retrieve current RepositoryState."""
        ...

    def save_state(self, state: RepositoryState) -> None:
        """Save RepositoryState."""
        ...


@runtime_checkable
class TwinStorePort(Protocol):
    """Port for persistence and retrieval of TwinSnapshot entities."""

    def save_snapshot(self, snapshot: TwinSnapshot) -> None:
        """Persist a TwinSnapshot."""
        ...

    def get_snapshot(
        self,
        repository_id: RepositoryId,
        commit_sha: CommitSha,
    ) -> Optional[TwinSnapshot]:
        """Retrieve a persisted TwinSnapshot."""
        ...


@runtime_checkable
class TwinCacheStore(Protocol):
    """Port for durable content-addressed caching of TwinSnapshot entities."""

    def get(self, key: TwinCacheKey) -> Optional[TwinSnapshot]:
        """Retrieve a cached TwinSnapshot."""
        ...

    def put(self, key: TwinCacheKey, snapshot: TwinSnapshot) -> None:
        """Cache a TwinSnapshot."""
        ...

    def invalidate_by_commit(self, commit_sha: CommitSha) -> int:
        """Invalidate cache entries for a commit."""
        ...

    def clear(self) -> None:
        """Purge all entries from the twin cache."""
        ...


@runtime_checkable
class TwinRegistryPort(Protocol):
    """Port for tracking twin versions, schema versions, and supported capabilities."""

    def builder_version(self) -> ComponentVersion:
        """Return ComponentVersion of the twin builder."""
        ...

    def supported_capabilities(self) -> FrozenSet[str]:
        """Return supported capabilities set."""
        ...


@runtime_checkable
class SnapshotManagerPort(Protocol):
    """Port for managing twin snapshots (creation, loading, restoring, comparing)."""

    def create_snapshot(self, twin: RepositoryTwin) -> TwinSnapshot:
        """Create an immutable TwinSnapshot."""
        ...

    def compare_snapshots(
        self,
        base_snapshot: TwinSnapshot,
        target_snapshot: TwinSnapshot,
    ) -> ChangeSet:
        """Compare two TwinSnapshots."""
        ...


@runtime_checkable
class SynchronizationPort(Protocol):
    """Port for synchronizing lower pipeline layers into the Digital Twin."""

    def synchronize(
        self,
        repository_id: RepositoryId,
        commit_sha: CommitSha,
    ) -> SynchronizationResult:
        """Orchestrate full layer synchronization."""
        ...


@runtime_checkable
class ConsistencyValidatorPort(Protocol):
    """Port for auditing cross-layer consistency (Repository ↔ Graph ↔ Semantic ↔ Parser)."""

    def validate_consistency(self, twin: RepositoryTwin) -> ConsistencyReport:
        """Perform cross-layer consistency validation."""
        ...


@runtime_checkable
class RepositoryMetricsPort(Protocol):
    """Port for computing deterministic RepositoryMetrics."""

    def compute_metrics(self, twin: RepositoryTwin) -> RepositoryMetrics:
        """Compute RepositoryMetrics from a RepositoryTwin."""
        ...


@runtime_checkable
class TwinLifecyclePort(Protocol):
    """Port for managing RepositoryTwin lifecycle transitions."""

    def transition_state(
        self,
        repository_id: RepositoryId,
        target_state: TwinState,
    ) -> RepositoryState:
        """Transition twin lifecycle state."""
        ...
