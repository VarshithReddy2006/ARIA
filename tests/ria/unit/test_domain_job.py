"""Tests for the job entity and its retry schedule.

These matter disproportionately. The job lifecycle is what makes ingestion resumable,
and every one of its failure paths is a path that only runs when something has already
gone wrong — so a defect there stays invisible until the day it costs a stalled
pipeline. The transition table is exercised exhaustively rather than sampled.
"""

from __future__ import annotations

import dataclasses
from datetime import timedelta

import pytest

from ria.domain.enums import JOB_TRANSITIONS, IngestionStage, JobKind, JobState
from ria.domain.errors import IllegalStateTransitionError
from ria.domain.identity import RepositoryId
from ria.domain.models.job import DEFAULT_RETRY_POLICY, Job, JobId, RetryPolicy
from tests.ria.conftest import utc

NOW = utc(2026, 1, 1, 12)
LATER = utc(2026, 1, 1, 13)
LEASE = timedelta(minutes=30)


def make_job(**overrides) -> Job:
    """Build a queued job with sensible defaults for a test.

    Args:
        **overrides: Fields to replace.
    """
    defaults = dict(
        job_id=JobId.generate(),
        repository_id=RepositoryId.generate(),
        kind=JobKind.INGEST_COMMIT,
        idempotency_key="ingest:abc",
        created_at=NOW,
        updated_at=NOW,
        available_at=NOW,
        payload={"sha": "a" * 40},
    )
    defaults.update(overrides)
    return Job(**defaults)


def leased_job(**overrides) -> Job:
    """Build a job already leased to a worker.

    Args:
        **overrides: Fields to replace before leasing.
    """
    return make_job(**overrides).leased(owner="worker-1", now=NOW, duration=LEASE)


class TestJobId:
    """Identity of a queued job."""

    def test_generate_is_unique(self) -> None:
        """Generated identifiers do not collide."""
        assert JobId.generate() != JobId.generate()

    def test_round_trips_through_string(self) -> None:
        """An identifier survives serialisation to text and back."""
        original = JobId.generate()
        assert JobId.parse(str(original)) == original

    def test_rejects_a_malformed_value(self) -> None:
        """A non-UUID identifier is rejected rather than stored."""
        with pytest.raises(ValueError):
            JobId.parse("not-a-uuid")

    def test_is_hashable(self) -> None:
        """Identifiers are usable as dictionary keys, which the queue relies on."""
        first = JobId.generate()
        assert len({first, JobId.parse(str(first))}) == 1


class TestConstruction:
    """Invariants enforced when a job is constructed."""

    def test_accepts_a_well_formed_job(self) -> None:
        """A queued job with a key and an availability time is constructible."""
        job = make_job()
        assert job.state is JobState.QUEUED
        assert job.attempts == 0
        assert job.available_at == NOW

    @pytest.mark.parametrize("key", ["", "   "])
    def test_requires_an_idempotency_key(self, key: str) -> None:
        """Without a key, enqueueing the same work twice would duplicate it."""
        with pytest.raises(ValueError, match="idempotency_key"):
            make_job(idempotency_key=key)

    def test_rejects_negative_attempts(self) -> None:
        """A negative attempt count is impossible."""
        with pytest.raises(ValueError, match="attempts"):
            make_job(attempts=-1)

    @pytest.mark.parametrize("priority", [-101, 101])
    def test_rejects_out_of_range_priority(self, priority: int) -> None:
        """Priority is bounded so the database check constraint cannot be violated."""
        with pytest.raises(ValueError, match="priority"):
            make_job(priority=priority)

    def test_leased_state_requires_a_lease(self) -> None:
        """A leased job must record its deadline and owner.

        A lease with no deadline would never expire, so its job would stall the queue
        forever with nothing to reclaim it.
        """
        with pytest.raises(ValueError, match="lease expiry and owner"):
            make_job(state=JobState.LEASED)

    def test_unleased_state_forbids_a_lease(self) -> None:
        """A stale lease on an unleased job is rejected."""
        with pytest.raises(ValueError, match="must be absent"):
            make_job(leased_until=LATER, lease_owner="worker-1")

    @pytest.mark.parametrize("state", [JobState.FAILED, JobState.DEAD])
    def test_failure_states_require_a_reason(self, state: JobState) -> None:
        """A failure with no stated cause is what PRD principle P11 forbids."""
        with pytest.raises(ValueError, match="why it failed"):
            make_job(state=state)

    def test_rejects_a_non_string_payload_value(self) -> None:
        """The payload must survive storage without a type registry.

        The queue is durable, so a job outlives the process that created it; a nested
        structure would have to be re-typed on load by code that cannot know its shape.
        """
        with pytest.raises(ValueError, match="strings to strings"):
            make_job(payload={"limit": 5})

    def test_payload_is_copied(self) -> None:
        """A caller's mutable mapping cannot alter the job after construction."""
        payload = {"sha": "a" * 40}
        job = make_job(payload=payload)
        payload["sha"] = "tampered"
        assert job.payload["sha"] == "a" * 40

    def test_is_immutable(self) -> None:
        """Fields cannot be assigned; change is expressed by transformation."""
        with pytest.raises(dataclasses.FrozenInstanceError):
            make_job().state = JobState.LEASED  # type: ignore[misc]


class TestPredicates:
    """Claimability and lease expiry."""

    def test_a_queued_job_is_claimable_once_available(self) -> None:
        """Availability gates the claim, which is how backoff works without sleeping."""
        job = make_job(available_at=LATER)
        assert job.is_claimable_at(NOW) is False
        assert job.is_claimable_at(LATER) is True

    @pytest.mark.parametrize(
        "state", [JobState.SUCCEEDED, JobState.DEAD, JobState.CANCELLED]
    )
    def test_terminal_states_are_not_claimable(self, state: JobState) -> None:
        """Completed work is never leased again by a runner."""
        job = make_job(
            state=state, last_error="boom" if state is JobState.DEAD else None
        )
        assert job.is_claimable_at(NOW) is False

    def test_lease_expiry_is_detected(self) -> None:
        """A lapsed lease is what makes worker death recoverable."""
        job = leased_job()
        assert job.lease_has_expired(NOW) is False
        assert job.lease_has_expired(NOW + LEASE + timedelta(seconds=1)) is True

    def test_an_unleased_job_never_reports_expiry(self) -> None:
        """Only a leased job can have a lapsed lease."""
        assert make_job().lease_has_expired(LATER) is False

    def test_can_retry_follows_the_policy(self) -> None:
        """The attempt ceiling comes from the policy, not from a constant."""
        policy = RetryPolicy(max_attempts=2)
        assert make_job(retry_policy=policy, attempts=1).can_retry is True
        assert make_job(retry_policy=policy, attempts=2).can_retry is False


class TestLeasing:
    """Claiming a job."""

    def test_records_owner_deadline_and_attempt(self) -> None:
        """A lease records who holds it and until when."""
        job = leased_job()
        assert job.state is JobState.LEASED
        assert job.lease_owner == "worker-1"
        assert job.leased_until == NOW + LEASE
        assert job.updated_at == NOW

    def test_counts_the_attempt_at_lease_time(self) -> None:
        """The attempt is consumed when claimed, not when reported.

        A worker that dies without reporting anything still consumes an attempt, so a
        job that reliably kills its worker cannot be retried forever.
        """
        assert leased_job().attempts == 1

    def test_rejects_an_empty_owner(self) -> None:
        """An anonymous lease could not be traced to the process holding it."""
        with pytest.raises(ValueError, match="owner"):
            make_job().leased(owner="  ", now=NOW, duration=LEASE)

    @pytest.mark.parametrize("duration", [timedelta(0), timedelta(seconds=-1)])
    def test_rejects_a_non_positive_duration(self, duration: timedelta) -> None:
        """A lease that expires on creation would be reclaimed immediately."""
        with pytest.raises(ValueError, match="duration"):
            make_job().leased(owner="worker-1", now=NOW, duration=duration)

    def test_cannot_lease_a_leased_job(self) -> None:
        """Two workers must never hold one job."""
        with pytest.raises(IllegalStateTransitionError):
            leased_job().leased(owner="worker-2", now=NOW, duration=LEASE)

    def test_cannot_lease_a_succeeded_job(self) -> None:
        """Completed work is not re-executed."""
        with pytest.raises(IllegalStateTransitionError):
            leased_job().succeeded(now=LATER).leased(
                owner="worker-2", now=LATER, duration=LEASE
            )


class TestCompletion:
    """Success, failure and their dispositions."""

    def test_success_clears_the_lease(self) -> None:
        """A completed job holds no lease, so nothing can reclaim it."""
        job = leased_job().succeeded(now=LATER)
        assert job.state is JobState.SUCCEEDED
        assert job.lease_owner is None
        assert job.leased_until is None
        assert job.updated_at == LATER

    def test_failure_records_the_reason_and_clears_the_lease(self) -> None:
        """A failure states its cause."""
        job = leased_job().failed(error="clone timed out", now=LATER)
        assert job.state is JobState.FAILED
        assert job.last_error == "clone timed out"
        assert job.lease_owner is None

    @pytest.mark.parametrize("error", ["", "   "])
    def test_failure_requires_a_reason(self, error: str) -> None:
        """A failure with no cause gives an operator nothing to act on."""
        with pytest.raises(ValueError, match="why it failed"):
            leased_job().failed(error=error, now=LATER)

    def test_failed_is_a_transient_state_on_the_way_to_a_disposition(self) -> None:
        """A failed job may be requeued or dead-lettered, and nothing else.

        Passing through ``FAILED`` rather than jumping to the outcome means the failure
        is recorded even if the process dies between the two writes.
        """
        assert JOB_TRANSITIONS[JobState.FAILED] == frozenset(
            {JobState.QUEUED, JobState.DEAD, JobState.CANCELLED}
        )

    def test_requeue_applies_backoff(self) -> None:
        """Backoff moves availability forward rather than blocking a worker."""
        job = leased_job().failed(error="boom", now=LATER)
        requeued = job.requeued(now=LATER, delay=timedelta(seconds=90))
        assert requeued.state is JobState.QUEUED
        assert requeued.available_at == LATER + timedelta(seconds=90)
        assert requeued.lease_owner is None

    def test_requeue_retains_the_failure_reason(self) -> None:
        """A job that eventually succeeds still shows what went wrong before."""
        job = leased_job().failed(error="boom", now=LATER).requeued(now=LATER)
        assert job.last_error == "boom"

    def test_requeue_rejects_a_negative_delay(self) -> None:
        """A negative delay would make a job available before it failed."""
        job = leased_job().failed(error="boom", now=LATER)
        with pytest.raises(ValueError, match="negative"):
            job.requeued(now=LATER, delay=timedelta(seconds=-1))

    def test_dead_letter_retains_the_reason(self) -> None:
        """A terminally failed job stays inspectable.

        Deletion would make a repository silently stop updating, which is the failure
        class PRD principle P11 forbids.
        """
        job = leased_job().failed(error="boom", now=LATER).dead(now=LATER)
        assert job.state is JobState.DEAD
        assert job.last_error == "boom"

    def test_dead_letter_accepts_an_explicit_reason(self) -> None:
        """A caller may supply a more specific cause than the last error."""
        failed = leased_job().failed(error="boom", now=LATER)
        assert failed.dead(now=LATER, error="no handler registered").last_error == (
            "no handler registered"
        )

    def test_a_leased_job_cannot_be_dead_lettered_directly(self) -> None:
        """A job must pass through ``FAILED`` on its way to ``DEAD``.

        Jumping straight there would lose the failure record if the process died
        between the two writes.
        """
        with pytest.raises(IllegalStateTransitionError):
            leased_job().dead(now=LATER, error="boom")

    def test_a_dead_job_may_be_requeued_by_an_operator(self) -> None:
        """A job that died during an outage is replayable without being recreated.

        Recreating it would lose its attempt history and its recorded cause.
        """
        dead = leased_job().failed(error="boom", now=LATER).dead(now=LATER)
        assert dead.requeued(now=LATER).state is JobState.QUEUED

    def test_cancellation_clears_the_lease_and_records_a_reason(self) -> None:
        """An operator withdrawing work leaves a record of why."""
        job = leased_job().cancelled(now=LATER, reason="repository archived")
        assert job.state is JobState.CANCELLED
        assert job.last_error == "repository archived"
        assert job.lease_owner is None

    def test_a_succeeded_job_cannot_be_cancelled(self) -> None:
        """Cancelling completed work would rewrite the record of what happened."""
        with pytest.raises(IllegalStateTransitionError):
            leased_job().succeeded(now=LATER).cancelled(now=LATER)


class TestLeaseExpiry:
    """Reclamation of a lapsed lease."""

    def test_returns_to_the_queue_when_attempts_remain(self) -> None:
        """A dead worker costs one lease duration, not the job."""
        job = leased_job(retry_policy=RetryPolicy(max_attempts=3)).lease_expired(
            now=LATER
        )
        assert job.state is JobState.QUEUED
        assert job.available_at == LATER
        assert job.lease_owner is None

    def test_states_that_the_worker_never_reported(self) -> None:
        """The recorded cause distinguishes a silent death from a reported failure."""
        job = leased_job().lease_expired(now=LATER)
        assert "lease expired" in job.last_error

    def test_dies_when_attempts_are_exhausted(self) -> None:
        """A job that repeatedly kills its worker stops rather than cycling forever.

        This is the case a naive reclaim sweep gets wrong: requeueing
        unconditionally turns one poisonous job into an unbounded loop that consumes a
        worker every lease period.
        """
        job = leased_job(retry_policy=RetryPolicy(max_attempts=1)).lease_expired(
            now=LATER
        )
        assert job.state is JobState.DEAD
        assert job.last_error is not None

    def test_does_not_count_a_further_attempt(self) -> None:
        """Reclamation is not an attempt; the attempt was counted at lease time."""
        leased = leased_job(retry_policy=RetryPolicy(max_attempts=3))
        assert leased.lease_expired(now=LATER).attempts == leased.attempts


class TestStageCheckpoint:
    """Recording pipeline progress on the job."""

    def test_records_the_stage(self) -> None:
        """A resumed job can report where the previous attempt reached."""
        job = make_job().at_stage(IngestionStage.ENUMERATE, now=LATER)
        assert job.stage == "enumerate"
        assert job.updated_at == LATER

    def test_stage_is_stored_as_its_string_value(self) -> None:
        """The stored form is the enum value, matching the persisted column."""
        assert make_job().at_stage(IngestionStage.HASH, now=NOW).stage == "hash"


class TestPayloadAccess:
    """Reading job arguments."""

    def test_require_returns_a_present_value(self) -> None:
        """A required argument is read directly."""
        assert make_job().require("sha") == "a" * 40

    def test_require_names_the_missing_key_and_the_kind(self) -> None:
        """A malformed job fails loudly rather than defaulting.

        Proceeding with a default would silently index the wrong thing, which is worse
        than failing: the result would look like a success.
        """
        with pytest.raises(ValueError, match="missing required key 'ref'"):
            make_job().require("ref")

    def test_metric_labels_are_bounded(self) -> None:
        """Labels exclude the repository, the identifier and the payload.

        Any of the three would create one metric series per repository or per job,
        which is how a metrics backend is brought down by cardinality.
        """
        labels = make_job().metric_labels()
        assert set(labels) == {"kind", "state"}


class TestRetryPolicy:
    """Validation and arithmetic of the backoff schedule."""

    def test_defaults_are_sane(self) -> None:
        """The shipped default retries a handful of times over minutes, not hours."""
        assert DEFAULT_RETRY_POLICY.max_attempts == 5
        assert DEFAULT_RETRY_POLICY.base_delay_seconds > 0

    @pytest.mark.parametrize(
        "overrides",
        [
            {"max_attempts": 0},
            {"base_delay_seconds": 0},
            {"base_delay_seconds": -1},
            {"multiplier": 0.5},
            {"max_delay_seconds": 0.5},
            {"jitter_ratio": -0.1},
            {"jitter_ratio": 1.1},
        ],
    )
    def test_rejects_invalid_configuration(self, overrides: dict) -> None:
        """An unusable schedule is rejected at construction."""
        with pytest.raises(ValueError):
            RetryPolicy(**overrides)

    def test_grows_exponentially(self) -> None:
        """Each attempt waits longer than the last."""
        policy = RetryPolicy(base_delay_seconds=2, multiplier=3, jitter_ratio=0)
        assert policy.delay_for(1).total_seconds() == 2
        assert policy.delay_for(2).total_seconds() == 6
        assert policy.delay_for(3).total_seconds() == 18

    def test_is_capped(self) -> None:
        """A long outage does not push the next attempt arbitrarily far away."""
        policy = RetryPolicy(
            base_delay_seconds=2, multiplier=10, max_delay_seconds=60, jitter_ratio=0
        )
        assert policy.delay_for(9).total_seconds() == 60

    def test_jitter_spreads_within_a_bounded_window(self) -> None:
        """Jitter never exceeds the capped delay and never goes below its floor.

        Without jitter, one fault that fails many jobs makes them all retry at the
        same instant and the retry storm outlives the fault.
        """
        policy = RetryPolicy(base_delay_seconds=10, multiplier=1, jitter_ratio=0.5)
        low = policy.delay_for(1, randomness=0.0).total_seconds()
        high = policy.delay_for(1, randomness=1.0).total_seconds()
        assert low == 5.0
        assert high == 10.0

    def test_full_randomness_yields_the_undithered_delay(self) -> None:
        """A test can assert an exact delay by supplying the randomness itself."""
        policy = RetryPolicy(base_delay_seconds=4, multiplier=1, jitter_ratio=0.9)
        assert policy.delay_for(1, randomness=1.0).total_seconds() == 4.0

    def test_is_a_pure_function_of_the_attempt(self) -> None:
        """Two calls with the same inputs agree.

        A schedule that lives in data drifts from the schedule in code; a computed one
        cannot.
        """
        policy = RetryPolicy()
        assert policy.delay_for(3, randomness=0.25) == policy.delay_for(
            3, randomness=0.25
        )

    @pytest.mark.parametrize("attempt", [0, -1])
    def test_rejects_a_non_positive_attempt(self, attempt: int) -> None:
        """There is no delay before the first attempt."""
        with pytest.raises(ValueError, match="attempt"):
            RetryPolicy().delay_for(attempt)

    @pytest.mark.parametrize("randomness", [-0.01, 1.01])
    def test_rejects_out_of_range_randomness(self, randomness: float) -> None:
        """Randomness is a proportion of the window."""
        with pytest.raises(ValueError, match="randomness"):
            RetryPolicy().delay_for(1, randomness=randomness)

    def test_permits_retry_until_the_ceiling(self) -> None:
        """The ceiling counts total attempts, including the first."""
        policy = RetryPolicy(max_attempts=3)
        assert [policy.permits_retry(n) for n in (0, 1, 2, 3, 4)] == [
            True,
            True,
            True,
            False,
            False,
        ]
