"""Unit tests for Phase 2 twin ports runtime conformance."""

from __future__ import annotations

from typing import FrozenSet, Optional

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
from ria.domain.models.twin_id import TwinId
from ria.domain.models.twin_identity import TwinCacheKey, TwinFingerprint
from ria.domain.models.twin_result import TwinMetadata, TwinStatistics
from ria.domain.models.twin_snapshot import TwinSnapshot
from ria.ports.twin import (
    ConsistencyValidatorPort,
    RepositoryMetricsPort,
    SnapshotManagerPort,
    SynchronizationPort,
    TwinBuilderPort,
    TwinCacheStore,
    TwinLifecyclePort,
    TwinRegistryPort,
    TwinRepositoryPort,
    TwinStorePort,
)


class DummyTwinBuilder:
    def build_twin(
        self,
        repository: Repository,
        commit_sha: CommitSha,
        graph_snapshot: GraphSnapshot,
    ) -> RepositoryTwin:
        tid = TwinId.for_repository(repository.id)
        state = RepositoryState(
            repository_id=repository.id, current_commit_sha=commit_sha
        )
        metrics = RepositoryMetrics()
        meta = TwinMetadata(repository.id.value, commit_sha.value)
        stats = TwinStatistics()
        return RepositoryTwin(
            tid, repository, state, graph_snapshot, metrics, meta, stats
        )

    def update_twin(
        self,
        previous_twin: RepositoryTwin,
        change_set: ChangeSet,
        updated_graph_snapshot: GraphSnapshot,
    ) -> RepositoryTwin:
        return previous_twin


class DummyTwinRepository:
    def get_state(self, repository_id: RepositoryId) -> Optional[RepositoryState]:
        return None

    def save_state(self, state: RepositoryState) -> None:
        pass


class DummyTwinStore:
    def save_snapshot(self, snapshot: TwinSnapshot) -> None:
        pass

    def get_snapshot(
        self, repository_id: RepositoryId, commit_sha: CommitSha
    ) -> Optional[TwinSnapshot]:
        return None


class DummyTwinCacheStore:
    def get(self, key: TwinCacheKey) -> Optional[TwinSnapshot]:
        return None

    def put(self, key: TwinCacheKey, snapshot: TwinSnapshot) -> None:
        pass

    def invalidate_by_commit(self, commit_sha: CommitSha) -> int:
        return 0

    def clear(self) -> None:
        pass


class DummyTwinRegistry:
    def builder_version(self) -> ComponentVersion:
        return ComponentVersion("dummy", "1.0.0")

    def supported_capabilities(self) -> FrozenSet[str]:
        return frozenset({"metrics", "validation"})


class DummySnapshotManager:
    def create_snapshot(self, twin: RepositoryTwin) -> TwinSnapshot:
        fp = TwinFingerprint("dummy")
        return TwinSnapshot(
            twin.twin_id, twin.repository.id, twin.state.current_commit_sha, twin, fp
        )

    def compare_snapshots(
        self, base_snapshot: TwinSnapshot, target_snapshot: TwinSnapshot
    ) -> ChangeSet:
        return ChangeSet(head_sha=target_snapshot.commit_sha.value)


class DummySynchronizationPort:
    def synchronize(
        self, repository_id: RepositoryId, commit_sha: CommitSha
    ) -> SynchronizationResult:
        return SynchronizationResult(repository_id=repository_id, commit_sha=commit_sha)


class DummyConsistencyValidator:
    def validate_consistency(self, twin: RepositoryTwin) -> ConsistencyReport:
        return ConsistencyReport()


class DummyRepositoryMetricsPort:
    def compute_metrics(self, twin: RepositoryTwin) -> RepositoryMetrics:
        return RepositoryMetrics()


class DummyTwinLifecycle:
    def transition_state(
        self, repository_id: RepositoryId, target_state: TwinState
    ) -> RepositoryState:
        return RepositoryState(
            repository_id=repository_id,
            current_commit_sha=CommitSha("a" * 40),
            twin_state=target_state,
        )


def test_twin_ports_conformance() -> None:
    assert isinstance(DummyTwinBuilder(), TwinBuilderPort)
    assert isinstance(DummyTwinRepository(), TwinRepositoryPort)
    assert isinstance(DummyTwinStore(), TwinStorePort)
    assert isinstance(DummyTwinCacheStore(), TwinCacheStore)
    assert isinstance(DummyTwinRegistry(), TwinRegistryPort)
    assert isinstance(DummySnapshotManager(), SnapshotManagerPort)
    assert isinstance(DummySynchronizationPort(), SynchronizationPort)
    assert isinstance(DummyConsistencyValidator(), ConsistencyValidatorPort)
    assert isinstance(DummyRepositoryMetricsPort(), RepositoryMetricsPort)
    assert isinstance(DummyTwinLifecycle(), TwinLifecyclePort)
