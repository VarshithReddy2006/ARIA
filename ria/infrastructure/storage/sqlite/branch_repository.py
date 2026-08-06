"""SQLite adapter for the branch store."""

from __future__ import annotations

import sqlite3
from typing import Optional, Sequence

from ria.domain.errors import StorageError
from ria.domain.identity import RepositoryId
from ria.domain.models.branch import Branch
from ria.infrastructure.storage.sqlite.mappers import branch_to_row, row_to_branch

__all__ = ["SqliteBranchStore"]

_COLUMNS = (
    "repository_id, name, head_sha, is_default, is_protected, "
    "last_commit_at, updated_at, merge_base_cache"
)


class SqliteBranchStore:
    """Persists :class:`~ria.domain.models.branch.Branch` in SQLite.

    Satisfies :class:`~ria.ports.repositories.BranchStore`.

    Args:
        connection: Connection owned by the enclosing unit of work.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def upsert(self, branch: Branch) -> None:
        """Insert or update a branch.

        Uses ``ON CONFLICT`` so that recording an observed pointer is one
        statement and one round trip. Branch discovery observes many branches at
        once, so halving the statement count per branch is worth the slightly
        longer SQL.

        Args:
            branch: Branch to record.

        Raises:
            StorageError: If the write fails, including when the write would give a
                repository two default branches.
        """
        row = branch_to_row(branch)
        placeholders = ", ".join(f":{column}" for column in row)
        assignments = ", ".join(
            f"{column} = excluded.{column}"
            for column in row
            if column not in ("repository_id", "name")
        )
        try:
            self._connection.execute(
                f"INSERT INTO ria_branch ({', '.join(row)}) VALUES ({placeholders}) "
                f"ON CONFLICT (repository_id, name) DO UPDATE SET {assignments}",
                row,
            )
        except sqlite3.Error as exc:
            raise StorageError(
                "branch could not be recorded",
                {
                    "repository_id": str(branch.repository_id),
                    "name": branch.name,
                    "reason": str(exc),
                },
            ) from exc

    def get(self, repository_id: RepositoryId, name: str) -> Optional[Branch]:
        """Load one branch by name.

        Args:
            repository_id: Owning repository.
            name: Branch name.

        Returns:
            The branch, or ``None`` if absent.
        """
        row = self._connection.execute(
            f"SELECT {_COLUMNS} FROM ria_branch WHERE repository_id = ? AND name = ?",
            (str(repository_id), name),
        ).fetchone()
        return row_to_branch(row) if row is not None else None

    def get_default(self, repository_id: RepositoryId) -> Optional[Branch]:
        """Load the repository's default branch.

        Args:
            repository_id: Owning repository.

        Returns:
            The default branch, or ``None`` if none is recorded.
        """
        row = self._connection.execute(
            f"SELECT {_COLUMNS} FROM ria_branch WHERE repository_id = ? AND is_default = 1",
            (str(repository_id),),
        ).fetchone()
        return row_to_branch(row) if row is not None else None

    def list(self, repository_id: RepositoryId) -> Sequence[Branch]:
        """List every recorded branch, ordered by name ascending.

        Args:
            repository_id: Owning repository.
        """
        rows = self._connection.execute(
            f"SELECT {_COLUMNS} FROM ria_branch WHERE repository_id = ? ORDER BY name ASC",
            (str(repository_id),),
        ).fetchall()
        return tuple(row_to_branch(row) for row in rows)

    def delete(self, repository_id: RepositoryId, name: str) -> bool:
        """Delete a branch record.

        Args:
            repository_id: Owning repository.
            name: Branch name.

        Returns:
            ``True`` if a record was removed.

        Raises:
            StorageError: If the delete fails.
        """
        try:
            cursor = self._connection.execute(
                "DELETE FROM ria_branch WHERE repository_id = ? AND name = ?",
                (str(repository_id), name),
            )
        except sqlite3.Error as exc:
            raise StorageError(
                "branch could not be deleted",
                {"repository_id": str(repository_id), "name": name, "reason": str(exc)},
            ) from exc
        return cursor.rowcount > 0

    def replace_all(
        self, repository_id: RepositoryId, branches: Sequence[Branch]
    ) -> None:
        """Replace the recorded branch set with the observed one.

        Deleting before inserting is deliberate. Upstream branch deletion can only
        be detected by comparing whole sets, and the partial unique index on the
        default branch would reject an insert that moves the default flag while the
        old holder still exists. Both statements run inside the caller's
        transaction, so no consumer observes an empty branch list.

        Args:
            repository_id: Owning repository.
            branches: The complete observed branch set.

        Raises:
            ValueError: If a branch belongs to a different repository, or more than
                one branch claims to be the default.
            StorageError: If the write fails.
        """
        for branch in branches:
            if branch.repository_id != repository_id:
                raise ValueError(
                    f"branch {branch.name!r} belongs to a different repository"
                )
        defaults = [branch.name for branch in branches if branch.is_default]
        if len(defaults) > 1:
            raise ValueError(f"more than one default branch supplied: {defaults}")

        try:
            self._connection.execute(
                "DELETE FROM ria_branch WHERE repository_id = ?", (str(repository_id),)
            )
        except sqlite3.Error as exc:
            raise StorageError(
                "existing branches could not be cleared",
                {"repository_id": str(repository_id), "reason": str(exc)},
            ) from exc
        for branch in branches:
            self.upsert(branch)
