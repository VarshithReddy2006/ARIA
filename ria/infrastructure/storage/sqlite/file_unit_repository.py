"""SQLite adapter for the file unit store.

The highest-volume table at Milestone 1: one row per file per indexed commit, so
a 100,000-file repository contributes 100,000 rows per commit. Every method here
is either bulk or narrowly scoped, and the two read paths that ingestion depends on
return primitive values rather than entities.
"""

from __future__ import annotations

import sqlite3
from typing import Dict, Optional, Sequence

from ria.domain.errors import StorageError
from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.file_unit import FileUnit
from ria.infrastructure.storage.sqlite.mappers import file_unit_to_row, row_to_file_unit

__all__ = ["SqliteFileUnitStore"]

_COLUMNS = (
    "repository_id, commit_sha, path, content_hash, blob_sha, language, "
    "language_tier, size_bytes, line_count, classification, parse_status, "
    "parse_status_reason, module_moniker"
)

#: Rows inserted per ``executemany`` batch. Bounded so that a very large tree does
#: not build one enormous parameter list, while remaining large enough that
#: per-statement overhead is amortised.
_INSERT_BATCH_SIZE = 5_000


class SqliteFileUnitStore:
    """Persists :class:`~ria.domain.models.file_unit.FileUnit` in SQLite.

    Satisfies :class:`~ria.ports.repositories.FileUnitStore`.

    Args:
        connection: Connection owned by the enclosing unit of work.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def add_many(self, units: Sequence[FileUnit]) -> int:
        """Insert file units in bulk.

        The batch is validated to belong to a single repository and commit before
        any write. A mixed batch almost certainly indicates a caller defect, and
        writing it would produce a manifest that is silently spread across two
        commits.

        Args:
            units: Units to insert.

        Returns:
            Number of rows inserted.

        Raises:
            ValueError: If the batch spans more than one repository or commit.
            StorageError: If the write fails.
        """
        if not units:
            return 0
        first = units[0]
        for unit in units:
            if (
                unit.repository_id != first.repository_id
                or unit.commit_sha != first.commit_sha
            ):
                raise ValueError(
                    "file unit batch must belong to a single repository and commit"
                )

        rows = [file_unit_to_row(unit) for unit in units]
        columns = list(rows[0])
        placeholders = ", ".join(f":{column}" for column in columns)
        statement = (
            f"INSERT INTO ria_file_unit ({', '.join(columns)}) VALUES ({placeholders})"
        )

        inserted = 0
        try:
            for start in range(0, len(rows), _INSERT_BATCH_SIZE):
                batch = rows[start : start + _INSERT_BATCH_SIZE]
                self._connection.executemany(statement, batch)
                inserted += len(batch)
        except sqlite3.Error as exc:
            raise StorageError(
                "file units could not be inserted",
                {
                    "repository_id": str(first.repository_id),
                    "commit_sha": str(first.commit_sha),
                    "reason": str(exc),
                },
            ) from exc
        return inserted

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
        row = self._connection.execute(
            f"SELECT {_COLUMNS} FROM ria_file_unit "
            "WHERE repository_id = ? AND commit_sha = ? AND path = ?",
            (str(repository_id), str(sha), path),
        ).fetchone()
        return row_to_file_unit(row) if row is not None else None

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

        Raises:
            ValueError: If the limit or offset is negative.
        """
        if limit < 0 or offset < 0:
            raise ValueError("limit and offset must be non-negative")
        rows = self._connection.execute(
            f"SELECT {_COLUMNS} FROM ria_file_unit "
            "WHERE repository_id = ? AND commit_sha = ? "
            "ORDER BY path ASC LIMIT ? OFFSET ?",
            (str(repository_id), str(sha), limit, offset),
        ).fetchall()
        return tuple(row_to_file_unit(row) for row in rows)

    def content_hashes_by_commit(
        self, repository_id: RepositoryId, sha: CommitSha
    ) -> Dict[str, str]:
        """Map every path in a commit to its content hash.

        Returns primitive strings rather than entities: change detection compares
        two hashes per path, and hydrating 100,000 entities to do that would
        dominate the incremental build budget of SDD section 1.1.

        Args:
            repository_id: Owning repository.
            sha: Commit to read.

        Returns:
            Mapping from path to content hash string.
        """
        rows = self._connection.execute(
            "SELECT path, content_hash FROM ria_file_unit "
            "WHERE repository_id = ? AND commit_sha = ?",
            (str(repository_id), str(sha)),
        ).fetchall()
        return {row["path"]: row["content_hash"] for row in rows}

    def count_by_commit(self, repository_id: RepositoryId, sha: CommitSha) -> int:
        """Count file units recorded for a commit.

        Args:
            repository_id: Owning repository.
            sha: Commit to count.
        """
        row = self._connection.execute(
            "SELECT COUNT(*) AS total FROM ria_file_unit "
            "WHERE repository_id = ? AND commit_sha = ?",
            (str(repository_id), str(sha)),
        ).fetchone()
        return int(row["total"])

    def delete_by_commit(self, repository_id: RepositoryId, sha: CommitSha) -> int:
        """Delete every file unit of a commit.

        Args:
            repository_id: Owning repository.
            sha: Commit whose units to delete.

        Returns:
            Number of rows deleted.

        Raises:
            StorageError: If the delete fails.
        """
        try:
            cursor = self._connection.execute(
                "DELETE FROM ria_file_unit WHERE repository_id = ? AND commit_sha = ?",
                (str(repository_id), str(sha)),
            )
        except sqlite3.Error as exc:
            raise StorageError(
                "file units could not be deleted",
                {
                    "repository_id": str(repository_id),
                    "commit_sha": str(sha),
                    "reason": str(exc),
                },
            ) from exc
        return cursor.rowcount
