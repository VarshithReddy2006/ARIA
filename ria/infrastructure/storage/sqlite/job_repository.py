"""SQLite adapter for the durable job queue.

Satisfies :class:`~ria.ports.job_store.JobStore`.

The claim is the whole design
-----------------------------
Everything else here is ordinary persistence; :meth:`SqliteJobStore.lease_next` is
the method the queue's correctness rests on. Two workers must never receive the same
job, and the guarantee comes from the enclosing unit of work having already acquired
SQLite's write lock at ``BEGIN IMMEDIATE``. The select and the update therefore occur
inside one exclusive write transaction, so a second worker's claim either waits or
sees the row already leased.

This is why the adapter does not open its own connection or manage its own
transaction: doing so would break the guarantee, because the claim would no longer
share a transaction with the caller's other writes.

Idempotency is delegated to a unique index rather than implemented as a
check-then-insert, for the same reason. A read followed by a write is not atomic, so
two simultaneous enqueues of one key would both pass the check.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence

from ria.domain.enums import JobKind, JobState
from ria.domain.errors import JobNotFoundError, StorageError
from ria.domain.identity import RepositoryId
from ria.domain.models.job import Job, JobId
from ria.infrastructure.storage.sqlite.mappers import job_to_row, row_to_job
from ria.observability.logging import get_logger

__all__ = ["SqliteJobStore"]

_LOGGER = get_logger(__name__)

_COLUMNS = (
    "job_id, repository_id, kind, idempotency_key, payload, state, priority, "
    "attempts, retry_policy, available_at, created_at, updated_at, leased_until, "
    "lease_owner, stage, last_error"
)

#: States a job may be cancelled from. Terminal states are excluded: cancelling a
#: succeeded job would rewrite the record of work that actually completed.
_CANCELLABLE = (JobState.QUEUED.value, JobState.LEASED.value, JobState.FAILED.value)


class SqliteJobStore:
    """Persists :class:`~ria.domain.models.job.Job` in SQLite.

    Args:
        connection: Connection owned by the enclosing unit of work.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    # -- enqueue ----------------------------------------------------------

    def enqueue(self, job: Job) -> Job:
        """Insert a job, or return the existing job with the same idempotency key.

        Args:
            job: Job to enqueue.

        Returns:
            The enqueued job, or the pre-existing job holding the same key.

        Raises:
            StorageError: If the write fails for any reason other than the
                idempotency constraint.
        """
        row = job_to_row(job)
        placeholders = ", ".join(f":{column}" for column in row)
        try:
            self._connection.execute(
                f"INSERT INTO ria_job ({', '.join(row)}) VALUES ({placeholders})", row
            )
        except sqlite3.IntegrityError as exc:
            existing = self.find_by_key(job.repository_id, job.idempotency_key)
            if existing is not None:
                _LOGGER.debug(
                    "job already queued for idempotency key",
                    extra={
                        "idempotency_key": job.idempotency_key,
                        "existing_job_id": str(existing.job_id),
                    },
                )
                return existing
            raise StorageError(
                "job could not be enqueued",
                {
                    "job_id": str(job.job_id),
                    "kind": job.kind.value,
                    "reason": str(exc),
                },
            ) from exc
        except sqlite3.Error as exc:
            raise StorageError(
                "job could not be enqueued",
                {"job_id": str(job.job_id), "reason": str(exc)},
            ) from exc
        return job

    # -- reads ------------------------------------------------------------

    def get(self, job_id: JobId) -> Optional[Job]:
        """Load a job by identifier.

        Args:
            job_id: Identifier to load.

        Returns:
            The job, or ``None`` if absent.
        """
        row = self._connection.execute(
            f"SELECT {_COLUMNS} FROM ria_job WHERE job_id = ?", (str(job_id),)
        ).fetchone()
        return row_to_job(row) if row is not None else None

    def find_by_key(
        self, repository_id: RepositoryId, idempotency_key: str
    ) -> Optional[Job]:
        """Load a job by its idempotency key.

        Args:
            repository_id: Owning repository.
            idempotency_key: Key supplied at enqueue time.

        Returns:
            The job, or ``None`` if absent.
        """
        row = self._connection.execute(
            f"SELECT {_COLUMNS} FROM ria_job "
            "WHERE repository_id = ? AND idempotency_key = ?",
            (str(repository_id), idempotency_key),
        ).fetchone()
        return row_to_job(row) if row is not None else None

    def list_by_state(
        self,
        state: JobState,
        *,
        repository_id: Optional[RepositoryId] = None,
        limit: int = 100,
    ) -> Sequence[Job]:
        """List jobs in a given state, most urgent first.

        Args:
            state: State to filter by.
            repository_id: Restrict to one repository.
            limit: Maximum number of records.

        Returns:
            Matching jobs.

        Raises:
            ValueError: If the limit is negative.
        """
        if limit < 0:
            raise ValueError("limit must be non-negative")
        clauses = ["state = ?"]
        parameters: List[object] = [state.value]
        if repository_id is not None:
            clauses.append("repository_id = ?")
            parameters.append(str(repository_id))
        parameters.append(limit)
        rows = self._connection.execute(
            f"SELECT {_COLUMNS} FROM ria_job WHERE {' AND '.join(clauses)} "
            "ORDER BY priority ASC, available_at ASC, created_at ASC LIMIT ?",
            tuple(parameters),
        ).fetchall()
        return tuple(row_to_job(row) for row in rows)

    def count_by_state(
        self, repository_id: Optional[RepositoryId] = None
    ) -> Dict[str, int]:
        """Count jobs per state.

        Args:
            repository_id: Restrict to one repository.

        Returns:
            Mapping from state value to count, omitting empty states.
        """
        if repository_id is None:
            rows = self._connection.execute(
                "SELECT state, COUNT(*) AS total FROM ria_job GROUP BY state"
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT state, COUNT(*) AS total FROM ria_job "
                "WHERE repository_id = ? GROUP BY state",
                (str(repository_id),),
            ).fetchall()
        return {row["state"]: int(row["total"]) for row in rows}

    # -- claim ------------------------------------------------------------

    def lease_next(
        self,
        *,
        owner: str,
        now: datetime,
        duration: timedelta,
        kinds: Optional[Sequence[JobKind]] = None,
        repository_id: Optional[RepositoryId] = None,
    ) -> Optional[Job]:
        """Claim the most urgent available job.

        Args:
            owner: Worker identifier.
            now: Current time. Jobs not yet available are skipped, which is how
                retry backoff is enforced without a worker sleeping.
            duration: How long the claim lasts.
            kinds: Restrict to these kinds.
            repository_id: Restrict to one repository.

        Returns:
            The leased job, or ``None`` if nothing is available.

        Raises:
            StorageError: If the claim fails.
        """
        clauses = ["state = ?", "available_at <= ?"]
        parameters: List[object] = [
            JobState.QUEUED.value,
            _encode(now),
        ]
        if kinds:
            placeholders = ", ".join("?" for _ in kinds)
            clauses.append(f"kind IN ({placeholders})")
            parameters.extend(kind.value for kind in kinds)
        if repository_id is not None:
            clauses.append("repository_id = ?")
            parameters.append(str(repository_id))

        row = self._connection.execute(
            f"SELECT {_COLUMNS} FROM ria_job WHERE {' AND '.join(clauses)} "
            # The third sort key makes the order total. Without it two equally
            # urgent jobs are returned in whatever order the storage engine
            # chooses, so claim order would vary between runs.
            "ORDER BY priority ASC, available_at ASC, created_at ASC LIMIT 1",
            tuple(parameters),
        ).fetchone()
        if row is None:
            return None

        leased = row_to_job(row).leased(owner=owner, now=now, duration=duration)
        self.save(leased)
        return leased

    # -- writes -----------------------------------------------------------

    def save(self, job: Job) -> None:
        """Persist a job's new state.

        Args:
            job: Job with its new state.

        Raises:
            JobNotFoundError: If the job is not present.
            StorageError: If the write fails.
        """
        row = job_to_row(job)
        assignments = ", ".join(
            f"{column} = :{column}" for column in row if column != "job_id"
        )
        try:
            cursor = self._connection.execute(
                f"UPDATE ria_job SET {assignments} WHERE job_id = :job_id", row
            )
        except sqlite3.Error as exc:
            raise StorageError(
                "job could not be updated",
                {"job_id": str(job.job_id), "reason": str(exc)},
            ) from exc
        if cursor.rowcount == 0:
            raise JobNotFoundError("job is not recorded", {"job_id": str(job.job_id)})

    def requeue_expired(self, *, now: datetime, limit: int = 100) -> Sequence[Job]:
        """Return jobs whose lease has lapsed to the queue.

        Args:
            now: Current time.
            limit: Maximum number of jobs to reclaim in one sweep.

        Returns:
            The reclaimed jobs in the state they now hold.

        Raises:
            ValueError: If the limit is negative.
            StorageError: If the sweep fails.
        """
        if limit < 0:
            raise ValueError("limit must be non-negative")
        rows = self._connection.execute(
            f"SELECT {_COLUMNS} FROM ria_job "
            "WHERE state = ? AND leased_until IS NOT NULL AND leased_until <= ? "
            "ORDER BY leased_until ASC LIMIT ?",
            (JobState.LEASED.value, _encode(now), limit),
        ).fetchall()

        reclaimed: List[Job] = []
        for row in rows:
            job = row_to_job(row).lease_expired(now=now)
            self.save(job)
            reclaimed.append(job)
        if reclaimed:
            _LOGGER.warning(
                "reclaimed jobs with expired leases",
                extra={
                    "count": len(reclaimed),
                    "job_ids": [str(job.job_id) for job in reclaimed],
                },
            )
        return tuple(reclaimed)

    def cancel_pending(self, repository_id: RepositoryId, *, now: datetime) -> int:
        """Cancel every job for a repository that has not yet completed.

        Cancellation goes through the entity rather than a bulk ``UPDATE``, so the
        transition table validates every one. A bulk statement would be faster and
        would bypass the lifecycle entirely, which is the trade this design refuses:
        the queue's states are the mechanism that keeps work from running twice.

        Args:
            repository_id: Owning repository.
            now: Current time, recorded as the cancellation time.

        Returns:
            Number of jobs cancelled.

        Raises:
            StorageError: If the write fails.
        """
        placeholders = ", ".join("?" for _ in _CANCELLABLE)
        rows = self._connection.execute(
            f"SELECT {_COLUMNS} FROM ria_job "
            f"WHERE repository_id = ? AND state IN ({placeholders})",
            (str(repository_id), *_CANCELLABLE),
        ).fetchall()
        cancelled = 0
        for row in rows:
            self.save(row_to_job(row).cancelled(now=now))
            cancelled += 1
        return cancelled

    def delete_by_repository(self, repository_id: RepositoryId) -> int:
        """Delete every job of a repository.

        Args:
            repository_id: Owning repository.

        Returns:
            Number of jobs deleted.

        Raises:
            StorageError: If the delete fails.
        """
        try:
            cursor = self._connection.execute(
                "DELETE FROM ria_job WHERE repository_id = ?", (str(repository_id),)
            )
        except sqlite3.Error as exc:
            raise StorageError(
                "jobs could not be deleted",
                {"repository_id": str(repository_id), "reason": str(exc)},
            ) from exc
        return cursor.rowcount


def _encode(value: datetime) -> str:
    """Encode a timestamp for comparison against a stored column.

    Args:
        value: Timestamp to encode. Must be timezone-aware.

    Returns:
        ISO-8601 string in UTC, comparable lexicographically against stored values
        because every stored timestamp uses the same normalised representation.

    Raises:
        StorageError: If the timestamp is naive.
    """
    if value.tzinfo is None:
        raise StorageError(
            "refusing to compare against a naive datetime",
            {"value": value.isoformat()},
        )
    return value.astimezone(timezone.utc).isoformat()
