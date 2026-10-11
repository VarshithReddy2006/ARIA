"""SQLite Repository Lock Adapter implementing RepositoryLockPort."""

import sqlite3
import threading
import time
import uuid
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
        ttl_seconds REAL NOT NULL,
        owner_token TEXT
    );
    """

    def __init__(self, db_path: Path | str = ":memory:") -> None:
        self._db_path = str(db_path)
        self._persistent_conn: Optional[sqlite3.Connection] = None
        self._owned_tokens = threading.local()
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
                # Serialize schema inspection and migration across starting workers.
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(self.CREATE_TABLE_SQL)
                columns = {
                    row["name"]
                    for row in conn.execute("PRAGMA table_info(repository_lock)")
                }
                if "owner_token" not in columns:
                    # Old leases stay active until their TTL expires, but are not
                    # releasable because their acquiring owner cannot be identified.
                    conn.execute(
                        "ALTER TABLE repository_lock ADD COLUMN owner_token TEXT"
                    )
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
        owner_token = uuid.uuid4().hex
        repo_str = repo_id.repo_id.value
        # The release-by-repository API cannot distinguish nested acquisitions.
        # Require the owning thread to release its previous handle first, even
        # if that lease has expired in the database.
        if repo_str in self._tokens():
            return False

        with self._get_connection() as conn:
            try:
                # Dead lock recovery: remove expired locks
                conn.execute(
                    "DELETE FROM repository_lock WHERE repo_id = ? AND (? - acquired_at) >= ttl_seconds;",
                    (repo_str, now),
                )
                cursor = conn.execute(
                    "INSERT OR IGNORE INTO repository_lock (repo_id, acquired_at, ttl_seconds, owner_token) VALUES (?, ?, ?, ?);",
                    (repo_str, now, ttl_seconds, owner_token),
                )
                acquired = cursor.rowcount > 0
                if acquired:
                    self._tokens()[repo_str] = owner_token
                return acquired
            except sqlite3.Error as err:
                raise DatabaseError(
                    f"Failed to acquire lock for '{repo_str}': {err}"
                ) from err

    def release_lock(self, repo_id: RepositoryIdentity) -> None:
        """Release process lock held for repository."""
        repo_str = repo_id.repo_id.value
        owner_token = self._tokens().get(repo_str)
        if owner_token is None:
            return
        with self._get_connection() as conn:
            try:
                conn.execute(
                    "DELETE FROM repository_lock WHERE repo_id = ? AND owner_token = ?;",
                    (repo_str, owner_token),
                )
                self._tokens().pop(repo_str, None)
            except sqlite3.Error as err:
                raise DatabaseError(
                    f"Failed to release lock for '{repo_str}': {err}"
                ) from err

    def _tokens(self) -> dict[str, str]:
        """Return the current thread's owned lease tokens by repository."""
        if not hasattr(self._owned_tokens, "by_repo"):
            self._owned_tokens.by_repo = {}
        return self._owned_tokens.by_repo
