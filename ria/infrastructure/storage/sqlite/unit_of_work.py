"""SQLite unit of work.

Implements :class:`~ria.ports.unit_of_work.UnitOfWork` over one SQLite connection
and one explicit transaction.

Two properties are enforced rather than documented.

Rollback by default
    Leaving the block without calling :meth:`SqliteUnitOfWork.commit` rolls back.
    An exception, an early return and a forgotten commit therefore all abandon the
    work instead of half-applying it.
Stores unusable after exit
    Accessing a store outside an open scope raises. Without this, a leaked
    reference would write outside a transaction and the atomic visibility
    guarantee of SDD section 5.1 would hold only by convention.
"""

from __future__ import annotations

import sqlite3
from types import TracebackType
from typing import Optional, Type, TypeVar

from ria.domain.errors import StorageError
from ria.observability.logging import get_logger
from ria.infrastructure.storage.sqlite.branch_repository import SqliteBranchStore
from ria.infrastructure.storage.sqlite.commit_repository import SqliteCommitStore
from ria.infrastructure.storage.sqlite.connection import ConnectionProvider
from ria.infrastructure.storage.sqlite.file_unit_repository import SqliteFileUnitStore
from ria.infrastructure.storage.sqlite.job_repository import SqliteJobStore
from ria.infrastructure.storage.sqlite.repository_repository import (
    SqliteRepositoryStore,
)
from ria.ports.metrics import MetricsSink

__all__ = ["SqliteUnitOfWork", "SqliteUnitOfWorkFactory"]

_LOGGER = get_logger(__name__)

#: Metric names emitted by this adapter.
_METRIC_TRANSACTIONS = "ria_storage_transactions_total"
_METRIC_TRANSACTION_SECONDS = "ria_storage_transaction_seconds"

#: Type variable for the store accessor guard.
_StoreT = TypeVar("_StoreT")


class SqliteUnitOfWork:
    """A single SQLite transaction exposing every persistence port.

    Satisfies :class:`~ria.ports.unit_of_work.UnitOfWork`.

    Args:
        connections: Provider of the connection to use.
        metrics: Sink for transaction counts and durations.
    """

    def __init__(self, connections: ConnectionProvider, metrics: MetricsSink) -> None:
        self._connections = connections
        self._metrics = metrics
        self._connection: Optional[sqlite3.Connection] = None
        self._repositories: Optional[SqliteRepositoryStore] = None
        self._commits: Optional[SqliteCommitStore] = None
        self._branches: Optional[SqliteBranchStore] = None
        self._file_units: Optional[SqliteFileUnitStore] = None
        self._jobs: Optional[SqliteJobStore] = None
        self._committed = False
        self._closed = False
        self._timer = None

    # -- scope ------------------------------------------------------------

    def __enter__(self) -> "SqliteUnitOfWork":
        """Open the transaction and construct the stores.

        Returns:
            This unit of work.

        Raises:
            StorageError: If the transaction could not be started, or if the scope
                has already been used. A unit of work is single-use; reopening one
                would silently share a transaction between two logical operations.
        """
        if self._closed:
            raise StorageError("unit of work has already been closed")
        if self._connection is not None:
            raise StorageError("unit of work is already open")

        connection = self._connections.connection()
        try:
            # IMMEDIATE acquires the write lock at BEGIN rather than at the first
            # write. Deferring it means two concurrent workers can both read, then
            # both attempt to upgrade, and one fails late with a busy error after
            # doing all its work. Acquiring up front converts that into a bounded
            # wait governed by busy_timeout.
            connection.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as exc:
            raise StorageError(
                "transaction could not be started",
                {"database": str(self._connections.database_path), "reason": str(exc)},
            ) from exc

        self._connection = connection
        self._repositories = SqliteRepositoryStore(connection)
        self._commits = SqliteCommitStore(connection)
        self._branches = SqliteBranchStore(connection)
        self._file_units = SqliteFileUnitStore(connection)
        self._jobs = SqliteJobStore(connection)
        self._timer = self._metrics.timer(_METRIC_TRANSACTION_SECONDS)
        self._timer.__enter__()
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        """Close the scope, rolling back unless :meth:`commit` was called."""
        try:
            if not self._committed:
                self.rollback()
        finally:
            if self._timer is not None:
                self._timer.__exit__(exc_type, exc, traceback)
                self._timer = None
            self._connection = None
            self._repositories = None
            self._commits = None
            self._branches = None
            self._file_units = None
            self._jobs = None
            self._closed = True

    # -- transaction ------------------------------------------------------

    def commit(self) -> None:
        """Make every write in this scope durable and visible.

        Raises:
            StorageError: If the scope is not open or the commit fails.
        """
        connection = self._require_connection()
        try:
            connection.execute("COMMIT")
        except sqlite3.Error as exc:
            self.rollback()
            self._metrics.increment(_METRIC_TRANSACTIONS, labels={"outcome": "failed"})
            raise StorageError(
                "transaction could not be committed",
                {"database": str(self._connections.database_path), "reason": str(exc)},
            ) from exc
        self._committed = True
        self._metrics.increment(_METRIC_TRANSACTIONS, labels={"outcome": "committed"})

    def rollback(self) -> None:
        """Discard every write in this scope.

        Safe to call more than once and after :meth:`commit`. A rollback failure is
        logged rather than raised: it means the transaction was already closed, and
        raising here would mask whatever error caused the rollback.
        """
        if self._connection is None or self._committed:
            return
        try:
            self._connection.execute("ROLLBACK")
            self._metrics.increment(
                _METRIC_TRANSACTIONS, labels={"outcome": "rolled_back"}
            )
        except sqlite3.Error as exc:
            _LOGGER.warning(
                "transaction rollback failed",
                extra={
                    "database": str(self._connections.database_path),
                    "reason": str(exc),
                },
            )

    # -- stores -----------------------------------------------------------

    @property
    def repositories(self) -> SqliteRepositoryStore:
        """Repository aggregate store bound to this transaction.

        Raises:
            StorageError: If the scope is not open.
        """
        return self._require_store(self._repositories, "repositories")

    @property
    def commits(self) -> SqliteCommitStore:
        """Commit store bound to this transaction.

        Raises:
            StorageError: If the scope is not open.
        """
        return self._require_store(self._commits, "commits")

    @property
    def branches(self) -> SqliteBranchStore:
        """Branch store bound to this transaction.

        Raises:
            StorageError: If the scope is not open.
        """
        return self._require_store(self._branches, "branches")

    @property
    def file_units(self) -> SqliteFileUnitStore:
        """File unit store bound to this transaction.

        Raises:
            StorageError: If the scope is not open.
        """
        return self._require_store(self._file_units, "file_units")

    @property
    def jobs(self) -> SqliteJobStore:
        """Job queue bound to this transaction.

        Sharing the transaction with the aggregate stores is what makes a handler's
        completion atomic: the work it performed and the job record marking it done
        are committed together, so a crash between the two is impossible.

        It is also what makes :meth:`SqliteJobStore.lease_next` safe under
        concurrency, because the claim occurs inside the write lock this scope
        acquired at ``BEGIN IMMEDIATE``.

        Raises:
            StorageError: If the scope is not open.
        """
        return self._require_store(self._jobs, "jobs")

    def _require_connection(self) -> sqlite3.Connection:
        """Return the open connection, or raise if the scope is not open.

        Raises:
            StorageError: If the unit of work has not been entered or has exited.
        """
        if self._connection is None:
            raise StorageError("unit of work is not open; use it as a context manager")
        return self._connection

    @staticmethod
    def _require_store(store: Optional[_StoreT], name: str) -> _StoreT:
        """Return a store, or raise if the scope is not open.

        A plain ``assert`` is deliberately avoided: assertions are removed under
        ``python -O``, and this check guards the transactional guarantee rather
        than a developer expectation.

        Args:
            store: Store instance, or ``None`` when the scope is closed.
            name: Store name, used in the error context.

        Raises:
            StorageError: If the store is unavailable.
        """
        if store is None:
            raise StorageError(
                "unit of work is not open; use it as a context manager",
                {"store": name},
            )
        return store


class SqliteUnitOfWorkFactory:
    """Creates a fresh :class:`SqliteUnitOfWork` per call.

    Satisfies :class:`~ria.ports.unit_of_work.UnitOfWorkFactory`.

    Args:
        connections: Provider of per-thread connections.
        metrics: Sink passed to each unit of work.
    """

    def __init__(self, connections: ConnectionProvider, metrics: MetricsSink) -> None:
        self._connections = connections
        self._metrics = metrics

    def __call__(self) -> SqliteUnitOfWork:
        """Create a new transactional scope."""
        return SqliteUnitOfWork(self._connections, self._metrics)
