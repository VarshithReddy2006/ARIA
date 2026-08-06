"""Incremental Planner Port Protocol."""

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from ria.domain.snapshot.entities import RepositorySnapshot
from ria.domain.snapshot.value_objects import ChangedFile, IncrementalPlan
from ria.domain.sync.value_objects import CommitReference


@runtime_checkable
class IncrementalPlannerPort(Protocol):
    """Protocol constructing IncrementalPlan from snapshot, target commit, and changed files."""

    def build_plan(
        self,
        snapshot: RepositorySnapshot,
        to_commit: CommitReference,
        changed_files: Sequence[ChangedFile],
    ) -> IncrementalPlan:
        """Construct immutable IncrementalPlan for targeted reindexing."""
        ...
