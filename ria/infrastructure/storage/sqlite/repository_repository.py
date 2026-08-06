"""SQLite adapter for the repository aggregate store."""

from __future__ import annotations

import sqlite3
from typing import Optional, Sequence

from ria.domain.enums import RepositoryStatus
from ria.domain.errors import (
    RepositoryAlreadyExistsError,
    RepositoryNotFoundError,
    StorageError,
)
from ria.domain.identity import Moniker, RepositoryId
from ria.domain.models.repository import Repository
from ria.infrastructure.storage.sqlite.mappers import (
    repository_to_row,
    row_to_repository,
)

__all__ = ["SqliteRepositoryStore"]

_COLUMNS = (
    "repository_id, moniker, origin_url, default_branch, tenant_id, status, "
    "degraded_reason, index_policy, languages, frameworks, size_metrics, "
    "registered_at, updated_at, last_indexed_at, last_indexed_sha"
)


class SqliteRepositoryStore:
    """Persists :class:`~ria.domain.models.repository.Repository` in SQLite.

    Satisfies :class:`~ria.ports.repositories.RepositoryStore`.

    Bound to one connection, which is bound to one transaction managed by the
    unit of work. This adapter never begins or commits a transaction.

    Args:
        connection: Connection owned by the enclosing unit of work.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def add(self, repository: Repository) -> None:
        """Insert a newly registered repository.

        Args:
            repository: Repository to insert.

        Raises:
            RepositoryAlreadyExistsError: If the identifier or moniker is taken.
            StorageError: If the write fails.
        """
        row = repository_to_row(repository)
        placeholders = ", ".join(f":{column}" for column in row)
        try:
            self._connection.execute(
                f"INSERT INTO ria_repository ({', '.join(row)}) VALUES ({placeholders})",
                row,
            )
        except sqlite3.IntegrityError as exc:
            raise RepositoryAlreadyExistsError(
                "repository is already registered",
                {
                    "repository_id": str(repository.repository_id),
                    "moniker": str(repository.moniker),
                    "reason": str(exc),
                },
            ) from exc
        except sqlite3.Error as exc:
            raise StorageError(
                "repository could not be inserted",
                {"repository_id": str(repository.repository_id), "reason": str(exc)},
            ) from exc

    def save(self, repository: Repository) -> None:
        """Update an existing repository.

        Args:
            repository: Repository with its new state.

        Raises:
            RepositoryNotFoundError: If the repository is not present.
            StorageError: If the write fails.
        """
        row = repository_to_row(repository)
        assignments = ", ".join(
            f"{column} = :{column}" for column in row if column != "repository_id"
        )
        try:
            cursor = self._connection.execute(
                f"UPDATE ria_repository SET {assignments} WHERE repository_id = :repository_id",
                row,
            )
        except sqlite3.Error as exc:
            raise StorageError(
                "repository could not be updated",
                {"repository_id": str(repository.repository_id), "reason": str(exc)},
            ) from exc
        if cursor.rowcount == 0:
            raise RepositoryNotFoundError(
                "repository is not registered",
                {"repository_id": str(repository.repository_id)},
            )

    def get(self, repository_id: RepositoryId) -> Optional[Repository]:
        """Load a repository by identifier.

        Args:
            repository_id: Identifier to load.

        Returns:
            The repository, or ``None`` if absent.
        """
        row = self._connection.execute(
            f"SELECT {_COLUMNS} FROM ria_repository WHERE repository_id = ?",
            (str(repository_id),),
        ).fetchone()
        return row_to_repository(row) if row is not None else None

    def get_by_moniker(self, moniker: Moniker) -> Optional[Repository]:
        """Load a repository by its logical identity.

        Args:
            moniker: Repository moniker.

        Returns:
            The repository, or ``None`` if absent.
        """
        row = self._connection.execute(
            f"SELECT {_COLUMNS} FROM ria_repository WHERE moniker = ?", (str(moniker),)
        ).fetchone()
        return row_to_repository(row) if row is not None else None

    def list(
        self,
        *,
        tenant_id: Optional[str] = None,
        status: Optional[RepositoryStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[Repository]:
        """List repositories ordered by moniker ascending.

        Ordering is by moniker rather than insertion order so that pagination is
        stable and two identical queries return identical results, which the
        response caching of SDD section 5.5 depends on.

        Args:
            tenant_id: Restrict to one tenant.
            status: Restrict to one lifecycle state.
            limit: Maximum number of records.
            offset: Records to skip.

        Returns:
            Matching repositories.

        Raises:
            ValueError: If the limit or offset is negative.
        """
        if limit < 0 or offset < 0:
            raise ValueError("limit and offset must be non-negative")
        clauses, parameters = self._filters(tenant_id, status)
        query = (
            f"SELECT {_COLUMNS} FROM ria_repository{clauses} "
            "ORDER BY moniker ASC LIMIT ? OFFSET ?"
        )
        rows = self._connection.execute(query, (*parameters, limit, offset)).fetchall()
        return tuple(row_to_repository(row) for row in rows)

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
        clauses, parameters = self._filters(tenant_id, status)
        row = self._connection.execute(
            f"SELECT COUNT(*) AS total FROM ria_repository{clauses}", parameters
        ).fetchone()
        return int(row["total"])

    def delete(self, repository_id: RepositoryId) -> bool:
        """Purge a repository and, by cascade, every fact owned by it.

        Args:
            repository_id: Repository to purge.

        Returns:
            ``True`` if a repository was removed.

        Raises:
            StorageError: If the delete fails.
        """
        try:
            cursor = self._connection.execute(
                "DELETE FROM ria_repository WHERE repository_id = ?",
                (str(repository_id),),
            )
        except sqlite3.Error as exc:
            raise StorageError(
                "repository could not be deleted",
                {"repository_id": str(repository_id), "reason": str(exc)},
            ) from exc
        return cursor.rowcount > 0

    @staticmethod
    def _filters(
        tenant_id: Optional[str], status: Optional[RepositoryStatus]
    ) -> "tuple[str, tuple]":
        """Build a WHERE clause and its parameters.

        Args:
            tenant_id: Optional tenant filter.
            status: Optional status filter.

        Returns:
            The clause, empty when unfiltered, and its bound parameters.
        """
        conditions = []
        parameters: list = []
        if tenant_id is not None:
            conditions.append("tenant_id = ?")
            parameters.append(tenant_id)
        if status is not None:
            conditions.append("status = ?")
            parameters.append(status.value)
        clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        return clause, tuple(parameters)
