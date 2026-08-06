"""Entities for C5 Incremental Indexing & Snapshot Subsystem."""

from dataclasses import dataclass

from ria.domain.common.base import ValueObject
from ria.domain.common.value_objects import Timestamp
from ria.domain.snapshot.value_objects import RepositorySnapshotId, SnapshotMetadata
from ria.domain.sync.value_objects import (
    BranchReference,
    CommitReference,
    RepositoryIdentity,
)


@dataclass(frozen=True, slots=True)
class RepositorySnapshot(ValueObject):
    """Immutable aggregate entity representing a repository snapshot state at a specific commit."""

    snapshot_id: RepositorySnapshotId
    identity: RepositoryIdentity
    commit: CommitReference
    branch: BranchReference
    created_at: Timestamp
    metadata: SnapshotMetadata
