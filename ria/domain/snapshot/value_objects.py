"""Value Objects for C5 Incremental Indexing & Snapshot Subsystem."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple

from ria.domain.common.base import ValueObject
from ria.domain.index.value_objects import FilePath
from ria.domain.resolution.value_objects import SymbolMoniker
from ria.domain.snapshot.exceptions import InvalidSnapshotError
from ria.domain.sync.value_objects import CommitReference, RepositoryIdentity


class ChangedFileType(Enum):
    """Enumeration of Git file modification kinds."""

    ADDED = "ADDED"
    MODIFIED = "MODIFIED"
    DELETED = "DELETED"
    RENAMED = "RENAMED"
    MOVED = "MOVED"


@dataclass(frozen=True, slots=True)
class RepositorySnapshotId(ValueObject):
    """Immutable unique identifier for a repository snapshot."""

    value: str

    def _validate_invariants(self) -> None:
        if not self.value or not self.value.strip():
            raise InvalidSnapshotError("RepositorySnapshotId value cannot be empty.")


@dataclass(frozen=True, slots=True)
class SnapshotVersion(ValueObject):
    """Immutable version descriptor for a snapshot."""

    version_str: str = "v1.0"


@dataclass(frozen=True, slots=True)
class RepositoryVersion(ValueObject):
    """Immutable combined state descriptor (commit sha + branch name)."""

    commit_sha: str
    branch_name: str


@dataclass(frozen=True, slots=True)
class SnapshotMetadata(ValueObject):
    """Immutable metadata descriptor for a repository snapshot."""

    total_files: int
    total_symbols: int
    index_version: str = "c1_v2"
    fact_version: str = "c3_v2"


@dataclass(frozen=True, slots=True)
class ChangedFile(ValueObject):
    """Immutable change descriptor for a single repository file between two commits."""

    path: FilePath
    change_type: ChangedFileType
    old_path: Optional[FilePath] = None


@dataclass(frozen=True, slots=True)
class DependencyImpact(ValueObject):
    """Immutable dependency impact analysis result identifying symbols and files affected by a change."""

    affected_symbols: Tuple[SymbolMoniker, ...] = field(default_factory=tuple)
    affected_files: Tuple[FilePath, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class CacheInvalidationPlan(ValueObject):
    """Immutable query cache invalidation plan."""

    invalidated_queries: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class IncrementalPlan(ValueObject):
    """Immutable execution plan for incremental reindexing and delta resolution."""

    repo_id: RepositoryIdentity
    from_commit: CommitReference
    to_commit: CommitReference
    files_to_reindex: Tuple[FilePath, ...] = field(default_factory=tuple)
    files_to_delete: Tuple[FilePath, ...] = field(default_factory=tuple)
    affected_symbols: Tuple[SymbolMoniker, ...] = field(default_factory=tuple)
