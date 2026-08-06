"""Job runner.

Leases a job, dispatches it to a handler, and records the outcome. The other half of
the Job Orchestrator of SDD section 4, whose queue side lives in
:mod:`ria.ports.job_store`.

Why the runner owns the retry decision
--------------------------------------
A handler decides *whether* work succeeded; only the runner knows the attempt count,
the policy and the clock, so only the runner can decide whether a failure becomes a
retry or a dead letter. Pushing that decision into handlers would duplicate it once
per job kind and let the copies drift.

Failure is never silent
-----------------------
Every path records something. A handler exception becomes a ``FAILED`` transition
carrying the reason, then either a requeue with backoff or a dead letter that stays
queryable. A handler that is missing for a job kind dead-letters immediately rather
than leaving the job to be leased forever by workers that cannot run it. PRD principle
P11 forbids degradation that does not state its cause, and an unrunnable job silently
cycling through the queue is exactly that.

Cooperative cancellation
------------------------
The runner is a synchronous ``run_once`` plus a caller-driven loop rather than a
thread that owns its own lifetime. The caller therefore controls shutdown, and a
process can drain in-flight work by simply not calling ``run_once`` again. A runner
that managed its own thread would need a second cancellation mechanism to achieve the
same thing.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Mapping, Optional, Sequence

from ria.domain.enums import JobKind, JobState
from ria.domain.errors import RiaError
from ria.domain.identity import RepositoryId
from ria.domain.models.job import Job
from ria.observability.logging import get_logger, log_context
from ria.ports.clock import Clock
from ria.ports.metrics import MetricsSink
from ria.ports.unit_of_work import UnitOfWorkFactory

__all__ = ["JobHandler", "JobOutcome", "JobRunner"]

_LOGGER = get_logger(__name__)

#: Metric names emitted by the runner.
_METRIC_LEASED = "ria_jobs_leased_total"
_METRIC_COMPLETED = "ria_jobs_completed_total"
_METRIC_RECLAIMED = "ria_jobs_reclaimed_total"
_METRIC_HANDLER_SECONDS = "ria_job_handler_seconds"
_METRIC_QUEUE_DEPTH = "ria_job_queue_depth"

#: A handler performs the work a job describes. It returns nothing: the outcome is
#: success unless it raises, which keeps handlers from having to know the queue's
#: vocabulary.
JobHandler = Callable[[Job], None]

#: Source of jitter, injected so the runner stays deterministic under test.
RandomSource = Callable[[], float]


@dataclass(frozen=True)
class JobOutcome:
    """What the runner did with one job.

    Attributes:
        job: The job in its final state for this attempt.
        succeeded: Whether the handler completed without raising.
        error: The failure reason, when one occurred.
        will_retry: Whether the job was returned to the queue for another attempt.
        retry_after: When the job becomes claimable again, when it will retry.
        duration_seconds: How long the handler ran.
    """

    job: Job
    succeeded: bool
    error: Optional[str] = None
    will_retry: bool = False
    retry_after: Optional[datetime] = None
    duration_seconds: float = 0.0

    @property
    def is_dead(self) -> bool:
        """Whether the job exhausted its attempts and was dead-lettered."""
        return self.job.state is JobState.DEAD

    def __str__(self) -> str:
        if self.succeeded:
            return f"{self.job.kind} succeeded in {self.duration_seconds:.3f}s"
        disposition = "retrying" if self.will_retry else "dead"
        return f"{self.job.kind} failed ({disposition}): {self.error}"


class JobRunner:
    """Leases and executes queued jobs.

    Args:
        unit_of_work_factory: Creates a transaction per queue operation.
        clock: Source of timestamps.
        metrics: Sink for counts and durations.
        handlers: Handler per job kind. A kind absent from this mapping is
            dead-lettered rather than left in the queue, so a misconfigured worker
            fails visibly instead of stalling the pipeline.
        owner: Identifier of this worker, recorded on every lease so a stuck job is
            traceable to the process that claimed it.
        lease_duration: How long a claim lasts. Must exceed the longest expected
            handler run, or a healthy worker's lease will expire mid-flight and a
            second worker will duplicate its work.
        random_source: Supplies jitter in ``[0, 1]``.
    """

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        clock: Clock,
        metrics: MetricsSink,
        handlers: Mapping[JobKind, JobHandler],
        *,
        owner: str,
        lease_duration: timedelta = timedelta(minutes=30),
        random_source: Optional[RandomSource] = None,
    ) -> None:
        if not owner.strip():
            raise ValueError("owner must be non-empty")
        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock
        self._metrics = metrics
        self._handlers = dict(handlers)
        self._owner = owner
        self._lease_duration = lease_duration
        self._random = random_source or random.random

    @property
    def owner(self) -> str:
        """Identifier recorded on this runner's leases."""
        return self._owner

    @property
    def handled_kinds(self) -> Sequence[JobKind]:
        """Job kinds this runner can execute, in declaration order."""
        return tuple(self._handlers)

    # -- execution --------------------------------------------------------

    def run_once(
        self, *, repository_id: Optional[RepositoryId] = None
    ) -> Optional[JobOutcome]:
        """Lease and execute at most one job.

        Args:
            repository_id: Restrict to one repository, so a deployment can dedicate a
                worker to a large repository without starving the rest.

        Returns:
            The outcome, or ``None`` if no job was available.
        """
        job = self._lease(repository_id)
        if job is None:
            return None
        with log_context(job_id=str(job.job_id), job_kind=job.kind.value):
            return self._execute(job)

    def drain(
        self, *, limit: int = 100, repository_id: Optional[RepositoryId] = None
    ) -> Sequence[JobOutcome]:
        """Execute jobs until the queue is empty or a bound is reached.

        The bound is mandatory rather than optional. A handler that enqueues further
        work — commit discovery enqueues one ingestion job per commit — would otherwise
        let a single call run for the lifetime of the repository, and a caller that
        wanted to stop it would have no opportunity to.

        Args:
            limit: Maximum number of jobs to execute.
            repository_id: Restrict to one repository.

        Returns:
            The outcomes, in execution order.

        Raises:
            ValueError: If the limit is not positive.
        """
        if limit < 1:
            raise ValueError("limit must be positive")
        outcomes = []
        for _ in range(limit):
            outcome = self.run_once(repository_id=repository_id)
            if outcome is None:
                break
            outcomes.append(outcome)
        return tuple(outcomes)

    def reclaim_expired(self, *, limit: int = 100) -> Sequence[Job]:
        """Return jobs whose leases have lapsed to the queue.

        The mechanism that makes worker death survivable: a worker that dies holding a
        lease costs one lease duration. Without this sweep the job would stay claimed
        forever and the pipeline would stall with no error anywhere.

        Args:
            limit: Maximum number of jobs to reclaim.

        Returns:
            The reclaimed jobs in the state they now hold.
        """
        now = self._clock.now()
        with self._unit_of_work_factory() as unit_of_work:
            reclaimed = unit_of_work.jobs.requeue_expired(now=now, limit=limit)
            unit_of_work.commit()
        for job in reclaimed:
            self._metrics.increment(
                _METRIC_RECLAIMED,
                labels={"kind": job.kind.value, "state": job.state.value},
            )
        return reclaimed

    def report_queue_depth(
        self, *, repository_id: Optional[RepositoryId] = None
    ) -> Mapping[str, int]:
        """Publish queue depth per state as a gauge and return it.

        Queue depth is the signal an autoscaler acts on and the first thing an
        operator checks when ingestion appears stalled, so it is published rather than
        only returned.

        Args:
            repository_id: Restrict to one repository.

        Returns:
            Mapping from state value to count, omitting empty states.
        """
        with self._unit_of_work_factory() as unit_of_work:
            depth = unit_of_work.jobs.count_by_state(repository_id)
        for state in JobState:
            self._metrics.gauge(
                _METRIC_QUEUE_DEPTH,
                depth.get(state.value, 0),
                labels={"state": state.value},
            )
        return depth

    # -- internals --------------------------------------------------------

    def _lease(self, repository_id: Optional[RepositoryId]) -> Optional[Job]:
        """Claim the most urgent available job this runner can handle.

        The claim and its commit share one transaction, which is what guarantees two
        workers never receive the same job: SQLite's write lock is held from
        ``BEGIN IMMEDIATE`` until the commit.

        Args:
            repository_id: Restrict to one repository.

        Returns:
            The leased job, or ``None`` if nothing is available.
        """
        now = self._clock.now()
        with self._unit_of_work_factory() as unit_of_work:
            job = unit_of_work.jobs.lease_next(
                owner=self._owner,
                now=now,
                duration=self._lease_duration,
                kinds=tuple(self._handlers) or None,
                repository_id=repository_id,
            )
            unit_of_work.commit()
        if job is not None:
            self._metrics.increment(_METRIC_LEASED, labels={"kind": job.kind.value})
        return job

    def _execute(self, job: Job) -> JobOutcome:
        """Dispatch a leased job and record its outcome.

        Args:
            job: The leased job.

        Returns:
            The outcome.
        """
        handler = self._handlers.get(job.kind)
        if handler is None:
            return self._fail(
                job,
                error=(
                    f"no handler is registered for job kind {job.kind.value!r}; "
                    "this worker cannot execute it"
                ),
                duration=0.0,
                retryable=False,
            )

        started = self._clock.now()
        try:
            with self._metrics.timer(
                _METRIC_HANDLER_SECONDS, labels={"kind": job.kind.value}
            ):
                handler(job)
        except RiaError as exc:
            # A domain error's own classification is authoritative and is not
            # widened by remaining attempts. Combining the two would make every
            # permanent fault retryable while any attempt remained, which spends the
            # whole budget on a malformed payload or a withdrawn repository — faults
            # that cannot resolve themselves. The attempt ceiling is applied
            # separately in ``_fail``.
            return self._fail(
                job,
                error=f"{type(exc).__name__}: {exc}",
                duration=self._elapsed(started),
                retryable=exc.is_retryable,
            )
        except Exception as exc:
            # An unexpected exception is treated as retryable, because a transient
            # fault we failed to classify is more likely than a permanent one, and the
            # attempt ceiling bounds the cost of being wrong.
            return self._fail(
                job,
                error=f"{type(exc).__name__}: {exc}",
                duration=self._elapsed(started),
                retryable=True,
            )
        return self._succeed(job, duration=self._elapsed(started))

    def _succeed(self, job: Job, *, duration: float) -> JobOutcome:
        """Record a successful attempt.

        Args:
            job: The executed job.
            duration: Handler runtime in seconds.

        Returns:
            The outcome.
        """
        now = self._clock.now()
        completed = job.succeeded(now=now)
        with self._unit_of_work_factory() as unit_of_work:
            unit_of_work.jobs.save(completed)
            unit_of_work.commit()
        self._metrics.increment(
            _METRIC_COMPLETED, labels={"kind": job.kind.value, "outcome": "succeeded"}
        )
        _LOGGER.info("job succeeded", extra={"duration_seconds": round(duration, 3)})
        return JobOutcome(job=completed, succeeded=True, duration_seconds=duration)

    def _fail(
        self, job: Job, *, error: str, duration: float, retryable: bool
    ) -> JobOutcome:
        """Record a failed attempt and decide its disposition.

        The job passes through ``FAILED`` before reaching its disposition, so the
        failure is recorded even if the process dies between the two writes.

        Args:
            job: The executed job.
            error: Why the attempt failed.
            duration: Handler runtime in seconds.
            retryable: Whether another attempt is worth making.

        Returns:
            The outcome.
        """
        now = self._clock.now()
        failed = job.failed(error=error, now=now)
        will_retry = retryable and failed.can_retry

        if will_retry:
            delay = failed.retry_policy.delay_for(
                failed.attempts, randomness=self._clamped_random()
            )
            final = failed.requeued(now=now, delay=delay)
            retry_after: Optional[datetime] = final.available_at
        else:
            final = failed.dead(now=now, error=error)
            retry_after = None

        with self._unit_of_work_factory() as unit_of_work:
            unit_of_work.jobs.save(failed)
            unit_of_work.jobs.save(final)
            unit_of_work.commit()

        outcome_label = "retrying" if will_retry else "dead"
        self._metrics.increment(
            _METRIC_COMPLETED, labels={"kind": job.kind.value, "outcome": outcome_label}
        )
        log = _LOGGER.warning if will_retry else _LOGGER.error
        log(
            "job failed",
            extra={
                "attempts": final.attempts,
                "max_attempts": final.retry_policy.max_attempts,
                "disposition": outcome_label,
                "retry_after": retry_after.isoformat() if retry_after else None,
                "reason": error,
            },
        )
        return JobOutcome(
            job=final,
            succeeded=False,
            error=error,
            will_retry=will_retry,
            retry_after=retry_after,
            duration_seconds=duration,
        )

    def _elapsed(self, started: datetime) -> float:
        """Seconds since a start instant, floored at zero.

        Floored because an injected clock may be frozen, and a negative duration would
        violate the metrics contract.

        Args:
            started: Start instant.
        """
        return max(0.0, (self._clock.now() - started).total_seconds())

    def _clamped_random(self) -> float:
        """Draw jitter, clamped into ``[0, 1]``.

        Clamped rather than trusted: an injected source that returned a value outside
        the range would otherwise raise inside the retry path, converting a recoverable
        handler failure into an unrecoverable runner failure.
        """
        try:
            value = float(self._random())
        except Exception:  # pragma: no cover - defensive
            return 1.0
        return min(1.0, max(0.0, value))
