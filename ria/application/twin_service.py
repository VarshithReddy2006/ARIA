"""RepositoryTwinService facade application service (Phases 12 & 13).

Provides unified application interface for twin construction, snapshot management,
synchronization, metrics computation, consistency validation, lifecycle transitions,
and observability metrics emission.
"""

from __future__ import annotations

import time
from typing import Optional

from ria.application.repository_metrics_service import RepositoryMetricsService
from ria.application.repository_state_manager import RepositoryStateManager
from ria.application.twin_builder import TwinBuilderService
from ria.application.twin_consistency_validator import TwinConsistencyValidator
from ria.application.twin_registry import TwinRegistry
from ria.application.twin_snapshot_manager import TwinSnapshotManager
from ria.application.twin_synchronization_engine import SynchronizationEngine
from ria.application.twin_update_service import TwinUpdateService
from ria.domain.enums import TwinState
from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.consistency_report import ConsistencyReport
from ria.domain.models.graph_snapshot import GraphSnapshot
from ria.domain.models.repository import Repository
from ria.domain.models.repository_metrics import RepositoryMetrics
from ria.domain.models.repository_state import RepositoryState
from ria.domain.models.repository_twin import RepositoryTwin
from ria.domain.models.synchronization_result import SynchronizationResult
from ria.domain.models.twin_snapshot import TwinSnapshot
from ria.observability.metrics import NullMetricsSink
from ria.ports.metrics import MetricsSink
from ria.ports.twin import TwinCacheStore, TwinStorePort

__all__ = ["RepositoryTwinService"]


class RepositoryTwinService:
    """Facade service unifying all Digital Twin application capabilities with observability metrics."""

    def __init__(
        self,
        store: Optional[TwinStorePort] = None,
        cache_store: Optional[TwinCacheStore] = None,
        metrics_sink: Optional[MetricsSink] = None,
    ) -> None:
        self._store = store
        self._cache_store = cache_store
        self._metrics_sink = metrics_sink or NullMetricsSink()

        self._builder = TwinBuilderService()
        self._snapshot_mgr = TwinSnapshotManager(store=store, cache_store=cache_store)
        self._state_mgr = RepositoryStateManager()
        self._sync_engine = SynchronizationEngine(
            twin_builder=self._builder, snapshot_manager=self._snapshot_mgr
        )
        self._update_svc = TwinUpdateService(twin_builder=self._builder)
        self._metrics_svc = RepositoryMetricsService()
        self._validator = TwinConsistencyValidator()
        self._registry = TwinRegistry()

    def build_twin(
        self,
        repository: Repository,
        commit_sha: CommitSha,
        graph_snapshot: GraphSnapshot,
    ) -> RepositoryTwin:
        """Construct a complete RepositoryTwin."""
        t0 = time.perf_counter()
        twin = self._builder.build_twin(repository, commit_sha, graph_snapshot)
        elapsed = time.perf_counter() - t0
        self._metrics_sink.observe("ria.twin.build_time_seconds", elapsed)
        return twin

    def create_snapshot(self, twin: RepositoryTwin) -> TwinSnapshot:
        """Create and persist an immutable TwinSnapshot."""
        t0 = time.perf_counter()
        snapshot = self._snapshot_mgr.create_snapshot(twin)
        elapsed = time.perf_counter() - t0
        self._metrics_sink.observe("ria.twin.snapshot_creation_time_seconds", elapsed)
        return snapshot

    def load_snapshot(
        self,
        repository_id: RepositoryId,
        commit_sha: CommitSha,
    ) -> Optional[TwinSnapshot]:
        """Load a TwinSnapshot from cache or store."""
        snapshot = self._snapshot_mgr.load_snapshot(repository_id, commit_sha)
        if snapshot is not None:
            self._metrics_sink.increment("ria.twin.cache_hits")
        else:
            self._metrics_sink.increment("ria.twin.cache_misses")
        return snapshot

    def synchronize(
        self,
        repository_id: RepositoryId,
        commit_sha: CommitSha,
    ) -> SynchronizationResult:
        """Synchronize all pipeline layers into the Digital Twin."""
        t0 = time.perf_counter()
        res = self._sync_engine.synchronize(repository_id, commit_sha)
        elapsed = time.perf_counter() - t0
        self._metrics_sink.observe("ria.twin.synchronization_time_seconds", elapsed)
        return res

    def compute_metrics(self, twin: RepositoryTwin) -> RepositoryMetrics:
        """Compute RepositoryMetrics."""
        t0 = time.perf_counter()
        metrics = self._metrics_svc.compute_metrics(twin)
        elapsed = time.perf_counter() - t0
        self._metrics_sink.observe("ria.twin.metrics_computation_time_seconds", elapsed)
        return metrics

    def validate_consistency(self, twin: RepositoryTwin) -> ConsistencyReport:
        """Perform cross-layer consistency validation."""
        t0 = time.perf_counter()
        report = self._validator.validate_consistency(twin)
        elapsed = time.perf_counter() - t0
        self._metrics_sink.observe("ria.twin.validation_time_seconds", elapsed)
        return report

    def transition_state(
        self,
        repository_id: RepositoryId,
        target_state: TwinState,
    ) -> RepositoryState:
        """Transition twin lifecycle state."""
        return self._state_mgr.transition_state(repository_id, target_state)
