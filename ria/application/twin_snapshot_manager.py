"""Snapshot Manager application service.

Manages creation, retrieval, restoration, comparison, and versioning of TwinSnapshot entities.
Implements :class:`~ria.ports.twin.SnapshotManagerPort`.
"""

from __future__ import annotations

from typing import Optional

from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.change_set import ChangeSet
from ria.domain.models.repository_twin import RepositoryTwin
from ria.domain.models.twin_identity import TwinCacheKey, TwinFingerprint
from ria.domain.models.twin_snapshot import TwinSnapshot
from ria.ports.twin import SnapshotManagerPort, TwinCacheStore, TwinStorePort

__all__ = ["TwinSnapshotManager"]


class TwinSnapshotManager(SnapshotManagerPort):
    """Service for managing TwinSnapshot lifecycle operations."""

    def __init__(
        self,
        store: Optional[TwinStorePort] = None,
        cache_store: Optional[TwinCacheStore] = None,
        builder_name: str = "default-twin-builder",
    ) -> None:
        self._store = store
        self._cache = cache_store
        self._builder_name = builder_name

    def create_snapshot(self, twin: RepositoryTwin) -> TwinSnapshot:
        """Create an immutable TwinSnapshot for a RepositoryTwin."""
        fp = TwinFingerprint(builder_name=self._builder_name)
        snapshot = TwinSnapshot(
            twin_id=twin.twin_id,
            repository_id=twin.repository.repository_id,
            commit_sha=twin.state.current_commit_sha,
            twin=twin,
            fingerprint=fp,
        )

        if self._cache is not None:
            key = TwinCacheKey(
                repository_id=twin.repository.repository_id,
                commit_sha=twin.state.current_commit_sha,
                fingerprint=fp,
            )
            self._cache.put(key, snapshot)

        if self._store is not None:
            self._store.save_snapshot(snapshot)

        return snapshot

    def load_snapshot(
        self,
        repository_id: RepositoryId,
        commit_sha: CommitSha,
    ) -> Optional[TwinSnapshot]:
        """Load a persisted TwinSnapshot from cache or store."""
        fp = TwinFingerprint(builder_name=self._builder_name)

        if self._cache is not None:
            key = TwinCacheKey(
                repository_id=repository_id, commit_sha=commit_sha, fingerprint=fp
            )
            cached = self._cache.get(key)
            if cached is not None:
                return cached

        if self._store is not None:
            snapshot = self._store.get_snapshot(repository_id, commit_sha)
            if snapshot is not None and self._cache is not None:
                key = TwinCacheKey(
                    repository_id=repository_id, commit_sha=commit_sha, fingerprint=fp
                )
                self._cache.put(key, snapshot)
            return snapshot

        return None

    def restore_snapshot(
        self,
        repository_id: RepositoryId,
        commit_sha: CommitSha,
    ) -> RepositoryTwin:
        """Restore a RepositoryTwin from snapshot store or raise KeyError."""
        snapshot = self.load_snapshot(repository_id, commit_sha)
        if snapshot is None:
            raise KeyError(
                f"no twin snapshot found for {repository_id.value}@{commit_sha.value}"
            )
        return snapshot.twin

    def compare_snapshots(
        self,
        base_snapshot: TwinSnapshot,
        target_snapshot: TwinSnapshot,
    ) -> ChangeSet:
        """Compare two TwinSnapshots and compute delta ChangeSet."""
        base_files = {
            n.location_path
            for n in base_snapshot.twin.graph_snapshot.graph.nodes
            if n.location_path
        }
        target_files = {
            n.location_path
            for n in target_snapshot.twin.graph_snapshot.graph.nodes
            if n.location_path
        }

        added = target_files - base_files
        deleted = base_files - target_files

        return ChangeSet(
            head_sha=target_snapshot.commit_sha.value,
            base_sha=base_snapshot.commit_sha.value,
            added=frozenset(added),
            deleted=frozenset(deleted),
        )
