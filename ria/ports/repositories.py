"""Persistence ports, one per aggregate root.

Implements the Repository pattern adopted in SDD section 7: "Data access behind
interfaces per aggregate root. Enables the storage swap of section 6.2 and makes
layers testable without a database."

The storage swap is not hypothetical. SDD open question T2 asks whether relational
adjacency is sufficient at 10^8 edges, and records that the decision will be made
on measured evidence. These interfaces are what keep that decision a substitution
rather than a rewrite.

Naming
------
The Python-level name of a port is ``<Aggregate>Repository``. This collides
uncomfortably with the *domain* concept also called Repository (a git repository),
hence :class:`RepositoryStore` rather than ``RepositoryRepository``: clarity at
the call site outranks pattern-name fidelity.

Contract shared by every port
-----------------------------
* Reads return ``None`` for an absent entity; they do not raise. Absence is an
  ordinary outcome and forcing exception handling around it produces worse code.
* Writes are idempotent where the specification allows, so that a retried job
  cannot corrupt state (SDD section 4, Job Orchestrator: "Every task idempotent
  and resumable").
* No port commits a transaction. Transaction control belongs to
  :class:`~ria.ports.unit_of_work.UnitOfWork`, so a use case can span several
  aggregates atomically.
* Every method is scoped by repository identifier where the entity is
  repository-owned, which enforces the tenant and repository partitioning of SDD
  section 6.3 at the interface rather than by convention.
"""

from __future__ import annotations

from typing import Optional, Protocol, Sequence, runtime_checkable

from ria.domain.enums import CommitIndexState, RepositoryStatus
from ria.domain.identity import CommitSha, Moniker, RepositoryId
from ria.domain.models.branch import Branch
from ria.domain.models.commit import Commit
from ria.domain.models.file_unit import FileUnit
from ria.domain.models.repository import Repository

__all__ = ["RepositoryStore", "CommitStore", "BranchStore", "FileUnitStore"]


@runtime_checkable
class RepositoryStore(Protocol):
    """Persistence for the :class:`~ria.domain.models.repository.Repository` aggregate."""

    def add(self, repository: Repository) -> None:
        """Insert a newly registered repository.

        Args:
            repository: Repository to insert.

        Raises:
            RepositoryAlreadyExistsError: If the identifier or moniker is taken.
            StorageError: If the write fails.
        """
        ...

    def save(self, repository: Repository) -> None:
        """Update an existing repository.

        Args:
            repository: Repository with its new state.

        Raises:
            RepositoryNotFoundError: If the repository is not present.
            StorageError: If the write fails.
        """
        ...

    def get(self, repository_id: RepositoryId) -> Optional[Repository]:
        """Load a repository by identifier.

        Args:
            repository_id: Identifier to load.

        Returns:
            The repository, or ``None`` if absent.
        """
        ...

    def get_by_moniker(self, moniker: Moniker) -> Optional[Repository]:
        """Load a repository by its logical identity.

        Args:
            moniker: Repository moniker of the form ``repo:host:owner/name``.

        Returns:
            The repository, or ``None`` if absent.
        """
        ...

    def list(
        self,
        *,
        tenant_id: Optional[str] = None,
        status: Optional[RepositoryStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[Repository]:
        """List repositories in a deterministic order.

        Ordering is by moniker ascending, so that pagination is stable and two
        identical queries return byte-identical results — a precondition for the
        response caching of SDD section 5.5.

        Args:
            tenant_id: Restrict to one tenant.
            status: Restrict to one lifecycle state.
            limit: Maximum number of records.
            offset: Records to skip.

        Returns:
            Matching repositories.
        """
        ...

    def count(
        self,
        *,
        tenant_id: Optional[str] = None,
        status: Optional[RepositoryStatus] = None,
    ) -> int:
        """Count repositories matching a filter.

        Args:
            tenant_id: Restrict to one tenant.
            status: Restrict to one lifecycle state.
        """
        ...

    def delete(self, repository_id: RepositoryId) -> bool:
        """Purge a repository and every fact owned by it.

        Implements the terminal ``archived -> purged`` step of the repository
        lifecycle. Irreversible.

        Args:
            repository_id: Repository to purge.

        Returns:
            ``True`` if a repository was removed, ``False`` if it was absent.
        """
        ...


@runtime_checkable
class CommitStore(Protocol):
    """Persistence for the :class:`~ria.domain.models.commit.Commit` entity.

    Implementations must enforce fact immutability. Twin Spec section 3.2 requires
    that a commit is never updated after reaching ``queryable``; the adapter
    compares :meth:`~ria.domain.models.commit.Commit.facts_fingerprint` against
    the stored digest and raises
    :class:`~ria.domain.errors.ImmutableFactViolationError` on a mismatch.
    """

    def add(self, commit: Commit) -> None:
        """Insert a newly discovered commit.

        Args:
            commit: Commit to insert.

        Raises:
            StorageError: If a commit with the same identity already exists or the
                write fails.
        """
        ...

    def save(self, commit: Commit) -> None:
        """Update a commit's index state and measurements.

        Args:
            commit: Commit with its new state.

        Raises:
            CommitNotFoundError: If the commit is not present.
            ImmutableFactViolationError: If the commit's facts are frozen and the
                supplied facts differ from those stored.
            StorageError: If the write fails.
        """
        ...

    def upsert(self, commit: Commit) -> None:
        """Insert a commit, or update it if already present.

        Provided so that commit discovery is idempotent: re-running discovery over
        a range that has already been recorded must not fail.

        Args:
            commit: Commit to insert or update.

        Raises:
            ImmutableFactViolationError: If the commit's facts are frozen and the
                supplied facts differ from those stored.
            StorageError: If the write fails.
        """
        ...

    def get(self, repository_id: RepositoryId, sha: CommitSha) -> Optional[Commit]:
        """Load one commit.

        Args:
            repository_id: Owning repository.
            sha: Commit object name.

        Returns:
            The commit, or ``None`` if absent.
        """
        ...

    def exists(self, repository_id: RepositoryId, sha: CommitSha) -> bool:
        """Whether a commit is recorded.

        Args:
            repository_id: Owning repository.
            sha: Commit object name.
        """
        ...

    def list_by_state(
        self,
        repository_id: RepositoryId,
        state: CommitIndexState,
        *,
        limit: int = 100,
    ) -> Sequence[Commit]:
        """List commits in a given index state, oldest committed first.

        Oldest first because index work should proceed in history order: a later
        commit's incremental build reuses the earlier commit's parse cache.

        Args:
            repository_id: Owning repository.
            state: Index state to filter by.
            limit: Maximum number of records.

        Returns:
            Matching commits.
        """
        ...

    def latest_queryable(self, repository_id: RepositoryId) -> Optional[Commit]:
        """Most recently committed commit that is queryable.

        Args:
            repository_id: Owning repository.

        Returns:
            The commit, or ``None`` if the repository has no queryable commit.
        """
        ...

    def count_by_state(self, repository_id: RepositoryId) -> "dict[str, int]":
        """Count commits per index state.

        Feeds the ``index_status`` query primitive of Twin Spec section 7.2, which
        reports freshness and coverage to consumers.

        Args:
            repository_id: Owning repository.

        Returns:
            Mapping from index state value to count. States with no commits are
            omitted.
        """
        ...

    def delete_by_repository(self, repository_id: RepositoryId) -> int:
        """Delete every commit of a repository.

        Args:
            repository_id: Owning repository.

        Returns:
            Number of commits deleted.
        """
        ...


@runtime_checkable
class BranchStore(Protocol):
    """Persistence for the :class:`~ria.domain.models.branch.Branch` entity."""

    def upsert(self, branch: Branch) -> None:
        """Insert or update a branch.

        Upsert rather than separate insert and update because a branch is a
        pointer: branch discovery observes the current pointer and records it,
        and whether the branch was previously known is not interesting.

        Args:
            branch: Branch to record.

        Raises:
            StorageError: If the write fails.
        """
        ...

    def get(self, repository_id: RepositoryId, name: str) -> Optional[Branch]:
        """Load one branch by name.

        Args:
            repository_id: Owning repository.
            name: Branch name without a ``refs/heads/`` prefix.

        Returns:
            The branch, or ``None`` if absent.
        """
        ...

    def get_default(self, repository_id: RepositoryId) -> Optional[Branch]:
        """Load the repository's default branch.

        Args:
            repository_id: Owning repository.

        Returns:
            The default branch, or ``None`` if none is recorded.
        """
        ...

    def list(self, repository_id: RepositoryId) -> Sequence[Branch]:
        """List every recorded branch, ordered by name ascending.

        Args:
            repository_id: Owning repository.
        """
        ...

    def delete(self, repository_id: RepositoryId, name: str) -> bool:
        """Delete a branch record.

        Args:
            repository_id: Owning repository.
            name: Branch name.

        Returns:
            ``True`` if a record was removed.
        """
        ...

    def replace_all(
        self, repository_id: RepositoryId, branches: Sequence[Branch]
    ) -> None:
        """Replace the recorded branch set with the observed one.

        Branch deletion upstream must be reflected locally, and the only reliable
        way to detect it is to compare the whole observed set against the whole
        recorded set. Performed atomically so that a consumer never observes an
        empty branch list.

        Args:
            repository_id: Owning repository.
            branches: The complete observed branch set.

        Raises:
            StorageError: If the write fails.
        """
        ...


@runtime_checkable
class FileUnitStore(Protocol):
    """Persistence for the :class:`~ria.domain.models.file_unit.FileUnit` entity.

    File units are the highest-volume entity at Milestone 1: a 100,000-file
    repository contributes 100,000 rows per indexed commit. Every method here is
    therefore either bulk or narrowly scoped; there is deliberately no
    single-record insert.
    """

    def add_many(self, units: Sequence[FileUnit]) -> int:
        """Insert file units in bulk.

        Args:
            units: Units to insert. All must belong to the same repository and
                commit; implementations validate this rather than silently
                writing a mixed batch.

        Returns:
            Number of rows inserted.

        Raises:
            ValueError: If the batch spans more than one commit.
            StorageError: If the write fails.
        """
        ...

    def get(
        self, repository_id: RepositoryId, sha: CommitSha, path: str
    ) -> Optional[FileUnit]:
        """Load one file unit.

        Args:
            repository_id: Owning repository.
            sha: Commit the unit belongs to.
            path: Normalised repository-relative path.

        Returns:
            The unit, or ``None`` if absent.
        """
        ...

    def list_by_commit(
        self,
        repository_id: RepositoryId,
        sha: CommitSha,
        *,
        limit: int = 1000,
        offset: int = 0,
    ) -> Sequence[FileUnit]:
        """List file units of a commit, ordered by path ascending.

        Args:
            repository_id: Owning repository.
            sha: Commit to list.
            limit: Maximum number of records.
            offset: Records to skip.

        Returns:
            Matching units.
        """
        ...

    def content_hashes_by_commit(
        self, repository_id: RepositoryId, sha: CommitSha
    ) -> "dict[str, str]":
        """Map every path in a commit to its content hash.

        The input to change detection in Milestone 2. Returns primitive strings
        rather than entities because loading 100,000 full entities to compare two
        hashes each would dominate the incremental build budget.

        Args:
            repository_id: Owning repository.
            sha: Commit to read.

        Returns:
            Mapping from path to content hash string.
        """
        ...

    def count_by_commit(self, repository_id: RepositoryId, sha: CommitSha) -> int:
        """Count file units recorded for a commit.

        Args:
            repository_id: Owning repository.
            sha: Commit to count.
        """
        ...

    def delete_by_commit(self, repository_id: RepositoryId, sha: CommitSha) -> int:
        """Delete every file unit of a commit.

        Args:
            repository_id: Owning repository.
            sha: Commit whose units to delete.

        Returns:
            Number of rows deleted.
        """
        ...
