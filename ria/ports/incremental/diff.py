"""Diff Engine Port Protocol."""

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from ria.domain.snapshot.value_objects import ChangedFile
from ria.domain.sync.value_objects import CommitReference, RepositoryIdentity


@runtime_checkable
class DiffEnginePort(Protocol):
    """Protocol comparing Git commits to identify changed files."""

    def compute_diff(
        self,
        repo_id: RepositoryIdentity,
        from_commit: CommitReference,
        to_commit: CommitReference,
    ) -> Sequence[ChangedFile]:
        """Return sequence of ChangedFile descriptors between from_commit and to_commit."""
        ...
