"""SQLite adapter for the commit store.

Enforces the immutability rule of Twin Spec section 3.2: a commit's facts may not
change once it has reached ``queryable``. Every write path reads the stored fact
fingerprint first and refuses a mismatch. Enforcing this in the adapter rather
than only in the entity matters because the entity cannot know what was previously
stored, and an in-memory check would be bypassed by any code path that constructs
a fresh entity from re-observed git data.
"""

from __future__ import annotations

import sqlite3
from typing import Dict, Optional, Sequence

from ria.domain.enums import CommitIndexState
from ria.domain.errors import CommitNotFoundError, StorageError
from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.commit import Commit
from ria.infrastructure.storage.sqlite.mappers import commit_to_row, row_to_commit

__all__ = ["SqliteCommitStore"]

_COLUMNS = (
    "repository_id, sha, parents, tree_hash, author_name, author_email, "
    "committer_name, committer_email, authored_at, committed_at, message, "
    "files_changed, insertions, deletions, index_state, failure_reason, "
    "coverage, indexed_at"
)


class SqliteCommitStore:
    """Persists :class:`~ria.domain.models.commit.Commit` in SQLite.

    Satisfies :class:`~ria.ports.repositories.CommitStore`.

    Args:
        connection: Connection owned by the enclosing unit of work.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def add(self, commit: Commit) -> None:
        """Insert a newly discovered commit.

        Args:
            commit: Commit to insert.

        Raises:
            StorageError: If a commit with the same identity exists, or the write
                fails.
        """
        row = commit_to_row(commit)
        placeholders = ", ".join(f":{column}" for column in row)
        try:
            self._connection.execute(
                f"INSERT INTO ria_commit ({', '.join(row)}) VALUES ({placeholders})",
                row,
            )
        except sqlite3.IntegrityError as exc:
            raise StorageError(
                "commit could not be inserted",
                {
                    "repository_id": str(commit.repository_id),
                    "sha": str(commit.sha),
                    "reason": str(exc),
                },
            ) from exc
        except sqlite3.Error as exc:
            raise StorageError(
                "commit could not be inserted",
                {"sha": str(commit.sha), "reason": str(exc)},
            ) from exc

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
        stored = self._fact_state(commit.repository_id, commit.sha)
        if stored is None:
            raise CommitNotFoundError(
                "commit is not recorded",
                {"repository_id": str(commit.repository_id), "sha": str(commit.sha)},
            )
        self._assert_facts_unchanged(commit, stored)
        self._update(commit)

    def upsert(self, commit: Commit) -> None:
        """Insert a commit, or update it if already present.

        Idempotent so that re-running commit discovery over an already-recorded
        range cannot fail, as SDD section 4 requires of every task.

        Args:
            commit: Commit to insert or update.

        Raises:
            ImmutableFactViolationError: If the commit's facts are frozen and the
                supplied facts differ from those stored.
            StorageError: If the write fails.
        """
        stored = self._fact_state(commit.repository_id, commit.sha)
        if stored is None:
            self.add(commit)
            return
        self._assert_facts_unchanged(commit, stored)
        self._update(commit)

    def get(self, repository_id: RepositoryId, sha: CommitSha) -> Optional[Commit]:
        """Load one commit.

        Args:
            repository_id: Owning repository.
            sha: Commit object name.

        Returns:
            The commit, or ``None`` if absent.
        """
        row = self._connection.execute(
            f"SELECT {_COLUMNS} FROM ria_commit WHERE repository_id = ? AND sha = ?",
            (str(repository_id), str(sha)),
        ).fetchone()
        return row_to_commit(row) if row is not None else None

    def exists(self, repository_id: RepositoryId, sha: CommitSha) -> bool:
        """Whether a commit is recorded.

        Args:
            repository_id: Owning repository.
            sha: Commit object name.
        """
        row = self._connection.execute(
            "SELECT 1 FROM ria_commit WHERE repository_id = ? AND sha = ? LIMIT 1",
            (str(repository_id), str(sha)),
        ).fetchone()
        return row is not None

    def list_by_state(
        self,
        repository_id: RepositoryId,
        state: CommitIndexState,
        *,
        limit: int = 100,
    ) -> Sequence[Commit]:
        """List commits in a given index state, oldest committed first.

        Args:
            repository_id: Owning repository.
            state: Index state to filter by.
            limit: Maximum number of records.

        Returns:
            Matching commits.

        Raises:
            ValueError: If the limit is negative.
        """
        if limit < 0:
            raise ValueError("limit must be non-negative")
        rows = self._connection.execute(
            f"SELECT {_COLUMNS} FROM ria_commit "
            "WHERE repository_id = ? AND index_state = ? "
            "ORDER BY committed_at ASC, sha ASC LIMIT ?",
            (str(repository_id), state.value, limit),
        ).fetchall()
        return tuple(row_to_commit(row) for row in rows)

    def latest_queryable(self, repository_id: RepositoryId) -> Optional[Commit]:
        """Most recently committed commit that is queryable.

        Args:
            repository_id: Owning repository.

        Returns:
            The commit, or ``None`` if none is queryable.
        """
        row = self._connection.execute(
            f"SELECT {_COLUMNS} FROM ria_commit "
            "WHERE repository_id = ? AND index_state = ? "
            "ORDER BY committed_at DESC, sha ASC LIMIT 1",
            (str(repository_id), CommitIndexState.QUERYABLE.value),
        ).fetchone()
        return row_to_commit(row) if row is not None else None

    def count_by_state(self, repository_id: RepositoryId) -> Dict[str, int]:
        """Count commits per index state.

        Args:
            repository_id: Owning repository.

        Returns:
            Mapping from index state value to count, omitting empty states.
        """
        rows = self._connection.execute(
            "SELECT index_state, COUNT(*) AS total FROM ria_commit "
            "WHERE repository_id = ? GROUP BY index_state",
            (str(repository_id),),
        ).fetchall()
        return {row["index_state"]: int(row["total"]) for row in rows}

    def delete_by_repository(self, repository_id: RepositoryId) -> int:
        """Delete every commit of a repository.

        Args:
            repository_id: Owning repository.

        Returns:
            Number of commits deleted.

        Raises:
            StorageError: If the delete fails.
        """
        try:
            cursor = self._connection.execute(
                "DELETE FROM ria_commit WHERE repository_id = ?", (str(repository_id),)
            )
        except sqlite3.Error as exc:
            raise StorageError(
                "commits could not be deleted",
                {"repository_id": str(repository_id), "reason": str(exc)},
            ) from exc
        return cursor.rowcount

    # -- internals --------------------------------------------------------

    def _fact_state(
        self, repository_id: RepositoryId, sha: CommitSha
    ) -> Optional["tuple[str, str]"]:
        """Read the stored fingerprint and index state of a commit.

        Args:
            repository_id: Owning repository.
            sha: Commit object name.

        Returns:
            The fingerprint and index state, or ``None`` if the commit is absent.
        """
        row = self._connection.execute(
            "SELECT facts_fingerprint, index_state FROM ria_commit "
            "WHERE repository_id = ? AND sha = ?",
            (str(repository_id), str(sha)),
        ).fetchone()
        if row is None:
            return None
        return row["facts_fingerprint"], row["index_state"]

    @staticmethod
    def _assert_facts_unchanged(commit: Commit, stored: "tuple[str, str]") -> None:
        """Refuse a write that would rewrite frozen facts.

        Args:
            commit: Commit being written.
            stored: Stored fingerprint and index state.

        Raises:
            ImmutableFactViolationError: If the stored state freezes facts and the
                incoming facts differ.
            StorageError: If the stored index state is not a known member.
        """
        fingerprint, state_value = stored
        try:
            state = CommitIndexState(state_value)
        except ValueError as exc:
            raise StorageError(
                "stored commit has an unknown index state",
                {"sha": str(commit.sha), "index_state": state_value},
            ) from exc
        if state.facts_are_frozen:
            commit.assert_facts_match(fingerprint)

    def _update(self, commit: Commit) -> None:
        """Write a commit's mutable columns.

        Args:
            commit: Commit to write.

        Raises:
            StorageError: If the write fails.
        """
        row = commit_to_row(commit)
        assignments = ", ".join(
            f"{column} = :{column}"
            for column in row
            if column not in ("repository_id", "sha")
        )
        try:
            self._connection.execute(
                f"UPDATE ria_commit SET {assignments} "
                "WHERE repository_id = :repository_id AND sha = :sha",
                row,
            )
        except sqlite3.Error as exc:
            raise StorageError(
                "commit could not be updated",
                {"sha": str(commit.sha), "reason": str(exc)},
            ) from exc
