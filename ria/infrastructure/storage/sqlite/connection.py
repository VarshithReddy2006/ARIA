"""SQLite connection management.

Centralises the pragmas that make SQLite behave correctly under the ingestion
worker pool of SDD section 6.3. Each is a deliberate choice, not a default:

``journal_mode=WAL``
    Write-ahead logging lets readers proceed while a writer holds the write lock.
    Without it, every query blocks during an index build, which would make the
    p95 latency target of SDD section 1.1 unreachable during ingestion.
``foreign_keys=ON``
    Off by default in SQLite. The schema depends on cascade deletes for the
    terminal ``archived -> purged`` lifecycle step, and a foreign key that is
    declared but unenforced is worse than none: it implies a guarantee the
    database is not providing.
``busy_timeout``
    Brief write contention between workers should block, not fail. Without a
    timeout SQLite raises immediately, turning ordinary contention into a job
    failure.
``synchronous=NORMAL``
    With WAL this is durable against process crash, losing at most recently
    committed transactions on host power loss. Acceptable because every fact is
    reconstructible from git, which SDD section 6.2 designates the system of
    record.

Connections are per-thread, never shared. A single :class:`sqlite3.Connection` is
not safe to use concurrently, and sharing one is the defect that would make the
worker pool intermittently fail.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Optional

from ria.domain.errors import StorageError
from ria.observability.logging import get_logger

__all__ = ["ConnectionProvider", "row_factory"]

_LOGGER = get_logger(__name__)


def row_factory(cursor: sqlite3.Cursor, row: tuple) -> sqlite3.Row:
    """Row factory producing name-addressable rows.

    Used so that mappers read ``row["column"]`` rather than positional indices.
    Positional access silently breaks when a column is inserted, and that breakage
    surfaces as wrong data rather than an error.

    Args:
        cursor: Cursor the row came from.
        row: Raw row tuple.

    Returns:
        A :class:`sqlite3.Row`.
    """
    return sqlite3.Row(cursor, row)


class ConnectionProvider:
    """Creates and caches one SQLite connection per thread.

    Args:
        database_path: Path of the database file. Parent directories are created
            if absent.
        busy_timeout_ms: How long a writer waits for a competing writer.

    Raises:
        StorageError: If the database directory cannot be created.
    """

    def __init__(self, database_path: Path, *, busy_timeout_ms: int = 5_000) -> None:
        self._database_path = Path(database_path)
        self._busy_timeout_ms = busy_timeout_ms
        self._local = threading.local()
        try:
            self._database_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StorageError(
                "database directory could not be created",
                {"path": str(self._database_path.parent), "reason": str(exc)},
            ) from exc

    @property
    def database_path(self) -> Path:
        """Path of the database file."""
        return self._database_path

    def connection(self) -> sqlite3.Connection:
        """Return this thread's connection, opening it on first use.

        Returns:
            A configured connection owned by the calling thread.

        Raises:
            StorageError: If the connection could not be opened or configured.
        """
        existing: Optional[sqlite3.Connection] = getattr(
            self._local, "connection", None
        )
        if existing is not None:
            return existing
        connection = self._open()
        self._local.connection = connection
        return connection

    def close(self) -> None:
        """Close this thread's connection if one is open.

        Each thread must close its own connection; closing another thread's would
        be unsafe. A worker pool therefore calls this at the end of each worker's
        life, not once at shutdown.
        """
        existing: Optional[sqlite3.Connection] = getattr(
            self._local, "connection", None
        )
        if existing is None:
            return
        try:
            existing.close()
        except sqlite3.Error as exc:
            _LOGGER.warning(
                "sqlite connection could not be closed cleanly",
                extra={"path": str(self._database_path), "reason": str(exc)},
            )
        finally:
            self._local.connection = None

    def _open(self) -> sqlite3.Connection:
        """Open and configure a connection.

        Returns:
            The configured connection.

        Raises:
            StorageError: If the connection could not be opened or configured.
        """
        try:
            connection = sqlite3.connect(
                str(self._database_path),
                timeout=self._busy_timeout_ms / 1000.0,
                # Transactions are controlled explicitly by the unit of work, so
                # the driver's implicit transaction management is disabled.
                isolation_level=None,
                check_same_thread=True,
            )
            connection.row_factory = row_factory
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(f"PRAGMA busy_timeout={self._busy_timeout_ms}")
            connection.execute("PRAGMA synchronous=NORMAL")
            return connection
        except sqlite3.Error as exc:
            raise StorageError(
                "sqlite connection could not be opened",
                {"path": str(self._database_path), "reason": str(exc)},
            ) from exc
