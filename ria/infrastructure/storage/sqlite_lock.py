"""SQLite Repository Lock Adapter implementing RepositoryLockPort."""

import sqlite3
import time
from pathlib import Path
from typing import Optional

from ria.domain.sync.value_objects import RepositoryIdentity
from ria.infrastructure.exceptions import DatabaseError
from ria.ports.sync.lock import RepositoryLockPort


class SQLiteRepositoryLockAdapter(RepositoryLockPort):
    """SQLite process-safe repository locking adapter with TTL expiration."""

    CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS repository_lock (
        repo_id TEXT PRIMARY KEY,
        acquired_at REAL NOT NULL,
        ttl_seconds REAL NOT NULL
    );
    """

    def __init__(self, db_path: Path | str = ":memory:") -> None:
        self._db_path = str(db_path)
        self._persistent_conn: Optional[sqlite3.Connection] = None
        if self._db_path == ":memory:":
            self._persistent_conn = sqlite3.connect(":memory:")
            self._persistent_conn.row_factory = sqlite3.Row
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        try:
            if self._persistent_conn is not None:
                return self._persistent_conn
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error as err:
            raise DatabaseError(
                f"Failed to connect to SQLite lock DB '{self._db_path}': {err}"
            ) from err

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            try:
                conn.execute(self.CREATE_TABLE_SQL)
            except sqlite3.Error as err:
                raise DatabaseError(
                    f"Failed to initialize SQLite table 'repository_lock': {err}"
                ) from err

    def is_locked(self, repo_id: RepositoryIdentity) -> bool:
        """Check if repository currently has an active, non-expired lock."""
        now = time.monotonic()
        sql = "SELECT acquired_at, ttl_seconds FROM repository_lock WHERE repo_id = ?;"
        with self._get_connection() as conn:
            try:
                cursor = conn.execute(sql, (repo_id.repo_id.value,))
                row = cursor.fetchone()
                if row is None:
                    return False
                acquired_at: float = row["acquired_at"]
                ttl_seconds: float = row["ttl_seconds"]
                return (now - acquired_at) < ttl_seconds
            except sqlite3.Error as err:
                raise DatabaseError(
                    f"Failed to query lock status for '{repo_id.repo_id.value}': {err}"
                ) from err

    def acquire_lock(
        self, repo_id: RepositoryIdentity, ttl_seconds: float = 300.0
    ) -> bool:
        """Attempt to acquire process lock for repository with expiration timeout."""
        now = time.monotonic()
        repo_str = repo_id.repo_id.value

        with self._get_connection() as conn:
            try:
                # Dead lock recovery: remove expired locks
                conn.execute(
                    "DELETE FROM repository_lock WHERE repo_id = ? AND (? - acquired_at) >= ttl_seconds;",
                    (repo_str, now),
                )
                cursor = conn.execute(
                    "INSERT OR IGNORE INTO repository_lock (repo_id, acquired_at, ttl_seconds) VALUES (?, ?, ?);",
                    (repo_str, now, ttl_seconds),
                )
                return cursor.rowcount > 0
            except sqlite3.Error as err:
                raise DatabaseError(
                    f"Failed to acquire lock for '{repo_str}': {err}"
                ) from err

    def release_lock(self, repo_id: RepositoryIdentity) -> None:
        """Release process lock held for repository."""
        repo_str = repo_id.repo_id.value
        with self._get_connection() as conn:
            try:
                conn.execute(
                    "DELETE FROM repository_lock WHERE repo_id = ?;", (repo_str,)
                )
            except sqlite3.Error as err:
                raise DatabaseError(
                    f"Failed to release lock for '{repo_str}': {err}"
                ) from err
