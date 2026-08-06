"""Background job entity and its retry schedule.

Implements the Job Orchestrator of SDD section 4: "durable queue, workers,
idempotency, retry, cancel, priority", with the design note "Every task idempotent
and resumable". The lifecycle and the states themselves live in
:mod:`ria.domain.enums`; this module holds the entity that moves through them.

Why the job layer exists at all
-------------------------------
SDD section 2.2 records that the brief's layering has no job layer, and that without
one "ingestion runs inside request handlers, which pins the system to a single
process". That was the prior architecture's hardest ceiling: analysis ran inline in an
HTTP response generator, so it could not be retried, resumed, cancelled, prioritised
or distributed. Every property here exists to prevent that.

Leasing rather than dequeuing
----------------------------
A worker *leases* a job for a bounded period rather than removing it from the queue.
If the worker dies, the lease expires and the job returns to the queue. Dequeuing
would lose the job on any worker crash, and at-least-once delivery plus idempotent
tasks is a far simpler correctness argument than exactly-once delivery.

The attempt is counted at lease time, not at failure time. A worker that dies without
reporting anything still consumes an attempt, so a job that reliably kills its worker
cannot be retried forever.

Backoff is computed, not stored
-------------------------------
:meth:`RetryPolicy.delay_for` is a pure function of the attempt number. A schedule
that lives in data drifts from the schedule that lives in code; a computed one
cannot.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Dict, Mapping, Optional

from ria.domain.enums import (
    JOB_TRANSITIONS,
    IngestionStage,
    JobKind,
    JobState,
    assert_transition,
)
from ria.domain.errors import IllegalStateTransitionError
from ria.domain.identity import RepositoryId

__all__ = ["JobId", "RetryPolicy", "Job", "DEFAULT_RETRY_POLICY"]


@dataclass(frozen=True)
class JobId:
    """Identifier of a queued job.

    A value object rather than a bare string, for the same reason
    :class:`~ria.domain.identity.RepositoryId` is: a job identifier and an
    idempotency key are both opaque strings, and at a call site that takes several of
    them nothing would prevent transposing the two.
    """

    value: uuid.UUID

    @classmethod
    def generate(cls) -> "JobId":
        """Create a fresh random identifier."""
        return cls(uuid.uuid4())

    @classmethod
    def parse(cls, value: str) -> "JobId":
        """Parse an identifier from its canonical string form.

        Args:
            value: UUID string.

        Raises:
            ValueError: If the value is not a valid UUID.
        """
        return cls(uuid.UUID(value))

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class RetryPolicy:
    """Exponential backoff with proportional jitter.

    Attributes:
        max_attempts: Total attempts permitted, including the first.
        base_delay_seconds: Delay after the first failure.
        multiplier: Growth factor applied per subsequent failure.
        max_delay_seconds: Ceiling on any single delay, so a long-lived outage does
            not push the next attempt weeks away.
        jitter_ratio: Fraction of the computed delay that may be randomised away, in
            ``[0, 1]``.

    Why jitter is not optional
    --------------------------
    Without it, a fault that fails many jobs at once — an unreachable forge, an
    expired credential — makes every one of them retry at the same instant, and the
    retry storm outlives the fault. Jitter spreads them across the window. The
    randomness is supplied by the caller rather than drawn here, so the policy stays a
    pure function and a test can assert an exact delay.
    """

    max_attempts: int = 5
    base_delay_seconds: float = 2.0
    multiplier: float = 3.0
    max_delay_seconds: float = 900.0
    jitter_ratio: float = 0.5

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError(
                f"max_attempts must be at least 1, got {self.max_attempts}"
            )
        if self.base_delay_seconds <= 0:
            raise ValueError(
                f"base_delay_seconds must be positive, got {self.base_delay_seconds}"
            )
        if self.multiplier < 1:
            raise ValueError(f"multiplier must be at least 1, got {self.multiplier}")
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError("max_delay_seconds must be at least base_delay_seconds")
        if not 0.0 <= self.jitter_ratio <= 1.0:
            raise ValueError(
                f"jitter_ratio must be within [0, 1], got {self.jitter_ratio}"
            )

    def permits_retry(self, attempts: int) -> bool:
        """Whether a further attempt is permitted.

        Args:
            attempts: Number of attempts already made.
        """
        return attempts < self.max_attempts

    def delay_for(self, attempt: int, *, randomness: float = 1.0) -> timedelta:
        """Delay to apply before a given attempt.

        Args:
            attempt: Number of attempts already made, at least one.
            randomness: Value in ``[0, 1]`` supplied by the caller, normally from a
                random source. ``1.0`` yields the full undithered delay, which is what
                a test asserts against.

        Returns:
            The delay before the job becomes claimable again.

        Raises:
            ValueError: If the attempt count or randomness is out of range.
        """
        if attempt < 1:
            raise ValueError(f"attempt must be at least 1, got {attempt}")
        if not 0.0 <= randomness <= 1.0:
            raise ValueError(f"randomness must be within [0, 1], got {randomness}")
        uncapped = self.base_delay_seconds * (self.multiplier ** (attempt - 1))
        capped = min(uncapped, self.max_delay_seconds)
        floor = capped * (1.0 - self.jitter_ratio)
        return timedelta(seconds=floor + (capped - floor) * randomness)


#: Policy applied when a job is enqueued without an explicit one.
DEFAULT_RETRY_POLICY = RetryPolicy()


@dataclass(frozen=True)
class Job:
    """One unit of background work.

    Attributes:
        job_id: Opaque identifier.
        repository_id: Repository the work concerns. Every job kind is
            repository-scoped, which is what lets the queue be filtered per
            repository and cascade-deleted with it.
        kind: Work the job represents.
        idempotency_key: Caller-supplied key, unique per repository. Enqueueing an
            existing key returns the existing job rather than creating a duplicate.
        created_at: When the job was enqueued.
        updated_at: When the job last changed.
        available_at: Earliest time the job may be leased. Retry backoff is expressed
            by moving this forward, so a worker never sleeps to honour a delay.
        payload: Kind-specific arguments, flat strings only. The queue is durable, so
            a job outlives the process that created it and its payload must survive a
            round trip through storage without a type registry.
        state: Lifecycle position.
        priority: Lower values are leased first.
        attempts: Number of attempts already made.
        retry_policy: Backoff schedule and attempt ceiling.
        leased_until: Expiry of the current lease, or ``None`` when not leased.
        lease_owner: Identifier of the worker holding the lease.
        stage: Pipeline stage last reported, retained so a resumed job can report
            where the previous attempt reached rather than restarting silently.
        last_error: Why the most recent attempt failed. Retained after a later success
            so that a job which eventually succeeded still shows what went wrong.
    """

    job_id: JobId
    repository_id: RepositoryId
    kind: JobKind
    idempotency_key: str
    created_at: datetime
    updated_at: datetime
    available_at: datetime
    payload: Mapping[str, str] = field(default_factory=dict)
    state: JobState = JobState.QUEUED
    priority: int = 0
    attempts: int = 0
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    leased_until: Optional[datetime] = None
    lease_owner: Optional[str] = None
    stage: Optional[str] = None
    last_error: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.idempotency_key or not self.idempotency_key.strip():
            raise ValueError("idempotency_key must be non-empty")
        if self.attempts < 0:
            raise ValueError(f"attempts must be non-negative, got {self.attempts}")
        if not -100 <= self.priority <= 100:
            raise ValueError(
                f"priority must be within [-100, 100], got {self.priority}"
            )

        if self.state is JobState.LEASED:
            if self.leased_until is None or not self.lease_owner:
                raise ValueError("a leased job must record its lease expiry and owner")
        elif self.leased_until is not None or self.lease_owner is not None:
            raise ValueError(
                "lease expiry and owner must be absent unless the job is leased"
            )

        if self.state is JobState.DEAD and not self.last_error:
            raise ValueError("a dead job must record why it failed")
        if self.state is JobState.FAILED and not self.last_error:
            raise ValueError("a failed job must record why it failed")

        payload = dict(self.payload)
        for key, value in payload.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise ValueError(
                    "job payload must map strings to strings; the queue is durable "
                    "and a payload must survive storage without a type registry"
                )
        object.__setattr__(self, "payload", payload)

    # -- predicates -------------------------------------------------------

    def is_claimable_at(self, moment: datetime) -> bool:
        """Whether the job may be leased at a given instant.

        Args:
            moment: Instant to evaluate.
        """
        return self.state.is_claimable and self.available_at <= moment

    def lease_has_expired(self, moment: datetime) -> bool:
        """Whether a leased job's lease has lapsed.

        A lapsed lease means the worker died or stalled. The job returns to the queue,
        which is what makes worker failure recoverable without any coordination
        between workers.

        Args:
            moment: Instant to evaluate.
        """
        return (
            self.state is JobState.LEASED
            and self.leased_until is not None
            and self.leased_until <= moment
        )

    @property
    def can_retry(self) -> bool:
        """Whether the retry policy permits another attempt."""
        return self.retry_policy.permits_retry(self.attempts)

    # -- transitions ------------------------------------------------------

    def leased(self, *, owner: str, now: datetime, duration: timedelta) -> "Job":
        """Return a copy claimed by a worker, with the attempt counted.

        Args:
            owner: Identifier of the leasing worker, recorded so a stuck job is
                traceable to the process that claimed it.
            now: Current time.
            duration: How long the claim lasts.

        Returns:
            The leased job.

        Raises:
            IllegalStateTransitionError: If the job is not claimable.
            ValueError: If the owner is empty or the duration is not positive.
        """
        # Checked explicitly rather than through the transition table alone.
        # ``assert_transition`` treats a self-transition as an idempotent no-op,
        # which is correct for a commit re-asserting its state but wrong here: it
        # would let a second worker lease a job that is already leased, which is the
        # one outcome the whole leasing design exists to prevent.
        if self.state is not JobState.QUEUED:
            raise IllegalStateTransitionError(
                "Job", str(self.state), str(JobState.LEASED)
            )
        assert_transition("Job", self.state, JobState.LEASED, JOB_TRANSITIONS)
        if not owner.strip():
            raise ValueError("lease owner must be non-empty")
        if duration <= timedelta(0):
            raise ValueError("lease duration must be positive")
        return replace(
            self,
            state=JobState.LEASED,
            lease_owner=owner,
            leased_until=now + duration,
            attempts=self.attempts + 1,
            updated_at=now,
        )

    def succeeded(self, *, now: datetime) -> "Job":
        """Return a copy marked successful.

        Args:
            now: Completion time.
        """
        assert_transition("Job", self.state, JobState.SUCCEEDED, JOB_TRANSITIONS)
        return replace(
            self,
            state=JobState.SUCCEEDED,
            lease_owner=None,
            leased_until=None,
            updated_at=now,
        )

    def failed(self, *, error: str, now: datetime) -> "Job":
        """Return a copy marked failed, pending a retry decision.

        ``FAILED`` is transient by design: the runner immediately moves the job to
        ``QUEUED`` or ``DEAD`` depending on remaining attempts. Passing through it
        rather than jumping straight to the outcome means the failure is recorded even
        if the process dies between the two steps.

        Args:
            error: Why the attempt failed.
            now: Current time.

        Raises:
            ValueError: If no reason is supplied. A failure with no stated cause is
                exactly what PRD principle P11 forbids.
        """
        assert_transition("Job", self.state, JobState.FAILED, JOB_TRANSITIONS)
        if not error or not error.strip():
            raise ValueError("a failed job must record why it failed")
        return replace(
            self,
            state=JobState.FAILED,
            lease_owner=None,
            leased_until=None,
            last_error=error,
            updated_at=now,
        )

    def requeued(self, *, now: datetime, delay: timedelta = timedelta(0)) -> "Job":
        """Return a copy returned to the queue for another attempt.

        Args:
            now: Current time.
            delay: Backoff before the job becomes claimable again.

        Returns:
            The requeued job.

        Raises:
            IllegalStateTransitionError: If the current state cannot be requeued.
            ValueError: If the delay is negative.
        """
        assert_transition("Job", self.state, JobState.QUEUED, JOB_TRANSITIONS)
        if delay < timedelta(0):
            raise ValueError("retry delay must not be negative")
        return replace(
            self,
            state=JobState.QUEUED,
            lease_owner=None,
            leased_until=None,
            available_at=now + delay,
            updated_at=now,
        )

    def dead(self, *, now: datetime, error: Optional[str] = None) -> "Job":
        """Return a copy terminally failed but retained for inspection.

        ``DEAD`` rather than deletion is deliberate. A job that simply disappeared
        would make a repository silently stop updating, which is the failure class PRD
        principle P11 forbids; a dead job stays queryable and requeueable.

        Args:
            now: Current time.
            error: Why the job failed. Defaults to the recorded last error.

        Raises:
            ValueError: If no reason is available from either source.
        """
        assert_transition("Job", self.state, JobState.DEAD, JOB_TRANSITIONS)
        reason = error or self.last_error
        if not reason:
            raise ValueError("a dead job must record why it failed")
        return replace(
            self,
            state=JobState.DEAD,
            lease_owner=None,
            leased_until=None,
            last_error=reason,
            updated_at=now,
        )

    def cancelled(self, *, now: datetime, reason: Optional[str] = None) -> "Job":
        """Return a copy cancelled by an operator.

        Args:
            now: Current time.
            reason: Why the job was cancelled.
        """
        assert_transition("Job", self.state, JobState.CANCELLED, JOB_TRANSITIONS)
        return replace(
            self,
            state=JobState.CANCELLED,
            lease_owner=None,
            leased_until=None,
            last_error=reason or self.last_error,
            updated_at=now,
        )

    def lease_expired(self, *, now: datetime) -> "Job":
        """Return a copy reclaimed after its lease lapsed.

        Distinct from :meth:`failed`: nothing was reported, because the worker never
        reported anything. The attempt was already counted at lease time, so an
        unresponsive worker cannot cause unbounded retries — and when the attempts are
        exhausted the job is returned as dead rather than queued, so a job that
        repeatedly kills its worker stops rather than cycling forever.

        Args:
            now: Current time.

        Returns:
            The job, queued if attempts remain and dead if they do not.
        """
        note = "lease expired before the worker reported an outcome"
        if self.can_retry:
            return replace(
                self,
                state=JobState.QUEUED,
                lease_owner=None,
                leased_until=None,
                available_at=now,
                last_error=note,
                updated_at=now,
            )
        return replace(
            self,
            state=JobState.DEAD,
            lease_owner=None,
            leased_until=None,
            last_error=note,
            updated_at=now,
        )

    def at_stage(self, stage: IngestionStage, *, now: datetime) -> "Job":
        """Return a copy recording the pipeline stage currently in progress.

        Args:
            stage: Stage now being executed.
            now: Current time.
        """
        return replace(self, stage=stage.value, updated_at=now)

    # -- payload access ---------------------------------------------------

    def require(self, key: str) -> str:
        """Read a required payload value.

        Args:
            key: Payload key.

        Returns:
            The value.

        Raises:
            ValueError: If the key is absent. A job whose payload lacks a required
                argument is malformed and must fail loudly rather than proceed with a
                default that silently indexes the wrong thing.
        """
        if key not in self.payload:
            raise ValueError(
                f"job payload is missing required key {key!r} "
                f"for a {self.kind.value} job"
            )
        return self.payload[key]

    def metric_labels(self) -> Dict[str, str]:
        """Bounded-cardinality labels describing this job.

        Deliberately excludes the repository identifier, the identifier and the
        payload: all three are unbounded, and a metric labelled with any of them would
        create one series per repository or per job.
        """
        return {"kind": self.kind.value, "state": self.state.value}

    def __str__(self) -> str:
        return f"job({self.kind}, {self.state}, attempts={self.attempts})"
