"""SQLite Repository Registry Adapter implementing RepositoryRegistryPort."""

import sqlite3
from collections.abc import Sequence
from pathlib import Path
from typing import Optional

from ria.domain.common.value_objects import Timestamp, UUIDv4
from ria.domain.sync.entities import RepositoryState
from ria.domain.sync.value_objects import (
    BranchReference,
    CommitReference,
    RepositoryIdentity,
    RepositoryMetadata,
    SyncStatus,
)
from ria.infrastructure.exceptions import DatabaseError
from ria.ports.sync.registry import RepositoryRegistryPort


class SQLiteRepositoryRegistryAdapter(RepositoryRegistryPort):
    """SQLite implementation of RepositoryRegistryPort for atomic state persistence."""

    CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS repository_state (
        repo_id TEXT PRIMARY KEY,
        remote_url TEXT NOT NULL,
        name TEXT NOT NULL,
        status TEXT NOT NULL,
        file_count INTEGER NOT NULL,
        total_bytes INTEGER NOT NULL,
        default_branch TEXT NOT NULL,
        registered_at TEXT NOT NULL,
        current_branch TEXT,
        current_commit_sha TEXT,
        current_commit_time TEXT,
        last_synced_at TEXT
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
                f"Failed to connect to SQLite database '{self._db_path}': {err}"
            ) from err

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            try:
                conn.execute(self.CREATE_TABLE_SQL)
            except sqlite3.Error as err:
                raise DatabaseError(
                    f"Failed to initialize SQLite table 'repository_state': {err}"
                ) from err

    def save_state(self, state: RepositoryState) -> None:
        """Persist or update RepositoryState aggregate root."""
        sql = """
        INSERT INTO repository_state (
            repo_id, remote_url, name, status, file_count, total_bytes,
            default_branch, registered_at, current_branch, current_commit_sha,
            current_commit_time, last_synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(repo_id) DO UPDATE SET
            status=excluded.status,
            file_count=excluded.file_count,
            total_bytes=excluded.total_bytes,
            default_branch=excluded.default_branch,
            current_branch=excluded.current_branch,
            current_commit_sha=excluded.current_commit_sha,
            current_commit_time=excluded.current_commit_time,
            last_synced_at=excluded.last_synced_at;
        """
        curr_branch_name = state.current_branch.name if state.current_branch else None
        curr_sha = state.current_commit.sha if state.current_commit else None
        curr_time = (
            state.current_commit.committed_at.iso_format
            if state.current_commit
            else None
        )
        last_sync = state.last_synced_at.iso_format if state.last_synced_at else None

        with self._get_connection() as conn:
            try:
                conn.execute(
                    sql,
                    (
                        state.identity.repo_id.value,
                        state.identity.remote_url,
                        state.identity.name,
                        state.status.value,
                        state.metadata.file_count,
                        state.metadata.total_bytes,
                        state.metadata.default_branch,
                        state.metadata.registered_at.iso_format,
                        curr_branch_name,
                        curr_sha,
                        curr_time,
                        last_sync,
                    ),
                )
            except sqlite3.Error as err:
                raise DatabaseError(
                    f"Failed to save repository state for '{state.identity.repo_id.value}': {err}"
                ) from err

    def _row_to_state(self, row: sqlite3.Row) -> RepositoryState:
        identity = RepositoryIdentity(
            repo_id=UUIDv4(value=row["repo_id"]),
            remote_url=row["remote_url"],
            name=row["name"],
        )
        metadata = RepositoryMetadata(
            file_count=row["file_count"],
            total_bytes=row["total_bytes"],
            default_branch=row["default_branch"],
            registered_at=Timestamp(iso_format=row["registered_at"]),
        )
        status = SyncStatus(row["status"])

        current_commit: Optional[CommitReference] = None
        if row["current_commit_sha"] and row["current_commit_time"]:
            current_commit = CommitReference(
                sha=row["current_commit_sha"],
                committed_at=Timestamp(iso_format=row["current_commit_time"]),
            )

        current_branch: Optional[BranchReference] = None
        if row["current_branch"] and current_commit:
            current_branch = BranchReference(
                name=row["current_branch"],
                head_commit=current_commit,
            )

        last_synced_at: Optional[Timestamp] = None
        if row["last_synced_at"]:
            last_synced_at = Timestamp(iso_format=row["last_synced_at"])

        return RepositoryState(
            identity=identity,
            status=status,
            metadata=metadata,
            current_branch=current_branch,
            current_commit=current_commit,
            last_synced_at=last_synced_at,
        )

    def get_state(self, repo_id: RepositoryIdentity) -> Optional[RepositoryState]:
        """Load RepositoryState for a given identity, or None if not registered."""
        sql = "SELECT * FROM repository_state WHERE repo_id = ?;"
        with self._get_connection() as conn:
            try:
                cursor = conn.execute(sql, (repo_id.repo_id.value,))
                row = cursor.fetchone()
                if row is None:
                    return None
                return self._row_to_state(row)
            except sqlite3.Error as err:
                raise DatabaseError(
                    f"Failed to get repository state for '{repo_id.repo_id.value}': {err}"
                ) from err

    def list_all(self) -> Sequence[RepositoryState]:
        """Retrieve list of all registered repository states."""
        sql = "SELECT * FROM repository_state;"
        with self._get_connection() as conn:
            try:
                cursor = conn.execute(sql)
                rows = cursor.fetchall()
                return tuple(self._row_to_state(row) for row in rows)
            except sqlite3.Error as err:
                raise DatabaseError(
                    f"Failed to list all repository states: {err}"
                ) from err

    def delete_state(self, repo_id: RepositoryIdentity) -> bool:
        """Remove repository state record. Returns True if deleted, False if not found."""
        sql = "DELETE FROM repository_state WHERE repo_id = ?;"
        with self._get_connection() as conn:
            try:
                cursor = conn.execute(sql, (repo_id.repo_id.value,))
                return cursor.rowcount > 0
            except sqlite3.Error as err:
                raise DatabaseError(
                    f"Failed to delete repository state '{repo_id.repo_id.value}': {err}"
                ) from err
