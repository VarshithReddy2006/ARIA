"""Durable job queue port.

Implements the Job Orchestrator of SDD section 4: "durable queue, workers,
idempotency, retry, cancel, priority".

Why this is not a Repository-pattern store
------------------------------------------
It is kept out of :mod:`ria.ports.repositories` because a queue is not an aggregate
store. Leasing, availability windows and expiry sweeps are concepts no other store
has, and folding them in would widen an interface three of whose four
implementations would then declare methods they cannot meaningfully provide.

Concurrency contract
--------------------
:meth:`JobStore.lease_next` is the only method with a concurrency requirement, and it
is the one the whole design rests on: two workers calling it simultaneously must
never receive the same job. Implementations satisfy this by claiming inside the
enclosing transaction, which for SQLite means the write lock acquired at
``BEGIN IMMEDIATE``.

Idempotency contract
--------------------
:meth:`JobStore.enqueue` is keyed by ``(repository_id, idempotency_key)``. Enqueueing
an existing key returns the existing job untouched rather than raising or creating a
duplicate. This is what makes commit discovery safe to re-run: a second pass over an
already-queued range performs no writes.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Optional, Protocol, Sequence, runtime_checkable

from ria.domain.enums import JobKind, JobState
from ria.domain.identity import RepositoryId
from ria.domain.models.job import Job, JobId

__all__ = ["JobStore"]


@runtime_checkable
class JobStore(Protocol):
    """Durable, lease-based work queue."""

    def enqueue(self, job: Job) -> Job:
        """Insert a job, or return the existing job with the same idempotency key.

        Args:
            job: Job to enqueue.

        Returns:
            The enqueued job, or the pre-existing job holding the same
            ``(repository_id, idempotency_key)``. A caller distinguishes the two by
            comparing :attr:`~ria.domain.models.job.Job.job_id`.

        Raises:
            StorageError: If the write fails.
        """
        ...

    def get(self, job_id: JobId) -> Optional[Job]:
        """Load a job by identifier.

        Args:
            job_id: Identifier to load.

        Returns:
            The job, or ``None`` if absent.
        """
        ...

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
        ...

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

        Selection order is priority ascending, then ``available_at`` ascending, then
        ``created_at`` ascending. The final tie-break makes the order total, so two
        equally urgent jobs are claimed in the order they were enqueued rather than
        in whatever order the storage engine happens to return.

        Args:
            owner: Worker identifier, recorded on the lease so a stuck job is
                traceable to the process that claimed it.
            now: Current time. Jobs whose ``available_at`` is in the future are not
                claimable, which is how retry backoff is enforced without sleeping.
            duration: How long the claim lasts.
            kinds: Restrict to these kinds. ``None`` means any kind, which lets a
                deployment run dedicated workers per kind without a second queue.
            repository_id: Restrict to one repository.

        Returns:
            The leased job with its attempt count incremented, or ``None`` if nothing
            is available.

        Raises:
            StorageError: If the claim fails.
        """
        ...

    def save(self, job: Job) -> None:
        """Persist a job's new state.

        Args:
            job: Job with its new state.

        Raises:
            JobNotFoundError: If the job is not present.
            StorageError: If the write fails.
        """
        ...

    def requeue_expired(self, *, now: datetime, limit: int = 100) -> Sequence[Job]:
        """Return jobs whose lease has lapsed to the queue.

        The mechanism that makes worker death survivable. A worker that dies holding
        a lease costs one lease duration; without this sweep the job would remain
        claimed forever and the pipeline would stall silently.

        Args:
            now: Current time.
            limit: Maximum number of jobs to reclaim in one sweep.

        Returns:
            The jobs whose leases were reclaimed, in the state they now hold. A job
            with no attempts remaining is returned as dead rather than queued.

        Raises:
            StorageError: If the sweep fails.
        """
        ...

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
        """
        ...

    def count_by_state(
        self, repository_id: Optional[RepositoryId] = None
    ) -> Dict[str, int]:
        """Count jobs per state.

        Feeds queue depth reporting, which is the signal an autoscaler acts on and
        the first thing an operator checks when ingestion appears stalled.

        Args:
            repository_id: Restrict to one repository.

        Returns:
            Mapping from state value to count, omitting empty states.
        """
        ...

    def cancel_pending(self, repository_id: RepositoryId, *, now: datetime) -> int:
        """Cancel every job for a repository that has not yet completed.

        Called when a repository is paused or archived, so that queued work does not
        continue against a repository an operator has withdrawn.

        Args:
            repository_id: Owning repository.
            now: Current time, recorded as the cancellation time.

        Returns:
            Number of jobs cancelled.

        Raises:
            StorageError: If the write fails.
        """
        ...

    def delete_by_repository(self, repository_id: RepositoryId) -> int:
        """Delete every job of a repository.

        Args:
            repository_id: Owning repository.

        Returns:
            Number of jobs deleted.
        """
        ...
