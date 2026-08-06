"""Unit of work port.

Transaction control belongs here rather than in the individual persistence ports,
because a single use case frequently spans several aggregates and those writes
must land together.

The decisive case is atomic visibility. SDD section 5.1 step 9 requires that a
commit becomes queryable atomically: "There is no intermediate state in which a
consumer observes a half-built index. Partial-visibility is the most insidious
correctness bug available in this class of system: it produces answers that are
wrong in ways indistinguishable from right." Making a commit queryable means
writing its file units, its coverage and its index state in one transaction. That
requires a transaction boundary above the individual stores, which is this port.

Usage
-----
::

    with unit_of_work_factory() as uow:
        uow.commits.upsert(commit)
        uow.file_units.add_many(units)
        uow.jobs.save(job.succeeded(now=clock.now()))
        uow.commit()

Leaving the block without calling :meth:`UnitOfWork.commit` rolls back. The
default is therefore safe: an exception, an early return, or a forgotten commit
all abandon the work rather than half-applying it.
"""

from __future__ import annotations

from types import TracebackType
from typing import Optional, Protocol, Type, runtime_checkable

from ria.ports.job_store import JobStore
from ria.ports.repositories import (
    BranchStore,
    CommitStore,
    FileUnitStore,
    RepositoryStore,
)

__all__ = ["UnitOfWork", "UnitOfWorkFactory"]


@runtime_checkable
class UnitOfWork(Protocol):
    """A transactional scope exposing every persistence port.

    Implementations must roll back on exit unless :meth:`commit` was called, and
    must make the stores unusable after exit so that a leaked reference cannot
    write outside a transaction.
    """

    @property
    def repositories(self) -> RepositoryStore:
        """Repository aggregate store bound to this transaction."""
        ...

    @property
    def commits(self) -> CommitStore:
        """Commit store bound to this transaction."""
        ...

    @property
    def branches(self) -> BranchStore:
        """Branch store bound to this transaction."""
        ...

    @property
    def file_units(self) -> FileUnitStore:
        """File unit store bound to this transaction."""
        ...

    @property
    def jobs(self) -> JobStore:
        """Job queue bound to this transaction.

        The queue shares the transaction with the aggregate stores on purpose. A
        handler that finishes its work and marks its job succeeded must do both
        atomically, or a crash between the two would leave work that has been
        performed queued for a second run.
        """
        ...

    def commit(self) -> None:
        """Make every write in this scope durable and visible.

        Raises:
            StorageError: If the transaction could not be committed.
        """
        ...

    def rollback(self) -> None:
        """Discard every write in this scope.

        Must be safe to call more than once and after :meth:`commit`.
        """
        ...

    def __enter__(self) -> "UnitOfWork":
        """Open the transactional scope."""
        ...

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        """Close the scope, rolling back unless :meth:`commit` was called."""
        ...


@runtime_checkable
class UnitOfWorkFactory(Protocol):
    """Creates a fresh :class:`UnitOfWork` per call.

    A factory rather than a shared instance because a unit of work is
    single-transaction and single-threaded by nature. Sharing one across requests
    or workers would interleave unrelated writes into one transaction, which is
    the failure mode a shared mutable singleton produces and which SDD section 7
    explicitly rejects.
    """

    def __call__(self) -> UnitOfWork:
        """Create a new transactional scope."""
        ...
