"""Snapshot Manager implementing SnapshotManagerPort."""

from typing import Dict, Optional

from ria.domain.common.value_objects import Timestamp, UUIDv4
from ria.domain.snapshot.entities import RepositorySnapshot
from ria.domain.snapshot.value_objects import RepositorySnapshotId, SnapshotMetadata
from ria.domain.sync.value_objects import BranchReference, CommitReference, RepositoryIdentity
from ria.ports.common.clock import ClockPort
from ria.ports.incremental.snapshot import SnapshotManagerPort


class SnapshotManager(SnapshotManagerPort):
    """In-memory and persistent manager for repository snapshots."""

    def __init__(self, clock: ClockPort) -> None:
        self._clock = clock
        self._snapshots: Dict[str, list[RepositorySnapshot]] = {}

    def create_snapshot(
        self,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
        total_files: int,
        total_symbols: int,
    ) -> RepositorySnapshot:
        meta = SnapshotMetadata(total_files=total_files, total_symbols=total_symbols)
        snapshot = RepositorySnapshot(
            snapshot_id=RepositorySnapshotId(value=UUIDv4.generate().value),
            identity=repo_id,
            commit=commit,
            branch=BranchReference(name="main", head_commit=commit),
            created_at=self._clock.now_utc(),
            metadata=meta,
        )
        repo_val = repo_id.repo_id.value
        if repo_val not in self._snapshots:
            self._snapshots[repo_val] = []
        self._snapshots[repo_val].append(snapshot)
        return snapshot

    def get_latest_snapshot(
        self,
        repo_id: RepositoryIdentity,
    ) -> Optional[RepositorySnapshot]:
        repo_val = repo_id.repo_id.value
        history = self._snapshots.get(repo_val)
        if not history:
            return None
        return history[-1]
