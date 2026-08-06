"""Tests for the job runner.

Almost every test here exercises a failure path, because failure handling is the whole
reason the job layer exists. A runner that only works when handlers succeed provides
nothing that an inline function call did not already provide.
"""

from __future__ import annotations

from datetime import timedelta
from typing import List

import pytest

from ria.application.job_runner import JobRunner
from ria.domain.enums import JobKind, JobState
from ria.domain.errors import GitCommandError, RiaError
from ria.domain.identity import RepositoryId
from ria.domain.models.job import Job, JobId, RetryPolicy
from ria.observability.metrics import InMemoryMetricsSink
from tests.ria.conftest import utc
from tests.ria.fakes import FrozenClock, InMemoryUnitOfWorkFactory

NOW = utc(2026, 1, 1, 12)
REPOSITORY = RepositoryId.generate()


class PermanentError(RiaError):
    """A domain error that declares itself unworthy of a retry."""

    is_retryable = False


def make_job(**overrides) -> Job:
    """Build a queued job for the runner to lease.

    Args:
        **overrides: Fields to replace.
    """
    defaults = dict(
        job_id=JobId.generate(),
        repository_id=REPOSITORY,
        kind=JobKind.INGEST_COMMIT,
        idempotency_key=f"key-{JobId.generate()}",
        created_at=NOW,
        updated_at=NOW,
        available_at=NOW,
        payload={"sha": "a" * 40},
    )
    defaults.update(overrides)
    return Job(**defaults)


def enqueue(factory: InMemoryUnitOfWorkFactory, job: Job) -> Job:
    """Enqueue a job through a committed transaction.

    Args:
        factory: Unit of work factory.
        job: Job to enqueue.
    """
    with factory() as unit_of_work:
        stored = unit_of_work.jobs.enqueue(job)
        unit_of_work.commit()
    return stored


def build_runner(
    factory: InMemoryUnitOfWorkFactory,
    clock: FrozenClock,
    metrics: InMemoryMetricsSink,
    handlers,
    **overrides,
) -> JobRunner:
    """Build a runner with deterministic jitter.

    Randomness is pinned to ``1.0`` so a test asserts an exact retry delay rather
    than a range.
    """
    options = {"owner": "worker-1", "random_source": lambda: 1.0}
    options.update(overrides)
    return JobRunner(factory, clock, metrics, handlers, **options)


@pytest.fixture
def factory() -> InMemoryUnitOfWorkFactory:
    """A unit of work factory over fresh in-memory state."""
    return InMemoryUnitOfWorkFactory()


class TestConstruction:
    """Validation of runner configuration."""

    def test_rejects_an_empty_owner(
        self, factory: InMemoryUnitOfWorkFactory, clock: FrozenClock, metrics
    ) -> None:
        """An anonymous lease could not be traced to its process."""
        with pytest.raises(ValueError, match="owner"):
            JobRunner(factory, clock, metrics, {}, owner="  ")

    def test_rejects_a_non_positive_lease_duration(
        self, factory: InMemoryUnitOfWorkFactory, clock: FrozenClock, metrics
    ) -> None:
        """A lease expiring on creation would be reclaimed immediately."""
        with pytest.raises(ValueError, match="lease_duration"):
            JobRunner(
                factory, clock, metrics, {}, owner="w", lease_duration=timedelta(0)
            )

    def test_reports_the_kinds_it_handles(
        self, factory: InMemoryUnitOfWorkFactory, clock: FrozenClock, metrics
    ) -> None:
        """The handled set is inspectable, which the lease filter relies on."""
        runner = build_runner(
            factory, clock, metrics, {JobKind.INGEST_COMMIT: lambda job: None}
        )
        assert runner.handled_kinds == (JobKind.INGEST_COMMIT,)
        assert runner.owner == "worker-1"


class TestSuccess:
    """The happy path."""

    def test_returns_none_when_the_queue_is_empty(
        self, factory: InMemoryUnitOfWorkFactory, clock: FrozenClock, metrics
    ) -> None:
        """An idle worker reports nothing rather than blocking."""
        runner = build_runner(
            factory, clock, metrics, {JobKind.INGEST_COMMIT: lambda j: None}
        )
        assert runner.run_once() is None

    def test_executes_and_marks_the_job_succeeded(
        self, factory: InMemoryUnitOfWorkFactory, clock: FrozenClock, metrics
    ) -> None:
        """A handler that returns normally completes the job."""
        seen: List[Job] = []
        job = enqueue(factory, make_job())
        runner = build_runner(
            factory, clock, metrics, {JobKind.INGEST_COMMIT: seen.append}
        )
        outcome = runner.run_once()
        assert outcome is not None
        assert outcome.succeeded is True
        assert outcome.job.state is JobState.SUCCEEDED
        assert [handled.job_id for handled in seen] == [job.job_id]

    def test_the_handler_receives_the_leased_job(
        self, factory: InMemoryUnitOfWorkFactory, clock: FrozenClock, metrics
    ) -> None:
        """The handler sees the attempt count and payload, not the pre-lease copy."""
        seen: List[Job] = []
        enqueue(factory, make_job())
        build_runner(
            factory, clock, metrics, {JobKind.INGEST_COMMIT: seen.append}
        ).run_once()
        assert seen[0].state is JobState.LEASED
        assert seen[0].attempts == 1
        assert seen[0].lease_owner == "worker-1"

    def test_leases_only_kinds_it_can_handle(
        self, factory: InMemoryUnitOfWorkFactory, clock: FrozenClock, metrics
    ) -> None:
        """A worker does not claim work it cannot perform.

        Claiming it would hold the job for a lease period and then dead-letter it,
        starving a worker that could have run it.
        """
        enqueue(factory, make_job(kind=JobKind.DISCOVER_COMMITS))
        runner = build_runner(
            factory, clock, metrics, {JobKind.INGEST_COMMIT: lambda job: None}
        )
        assert runner.run_once() is None

    def test_can_be_restricted_to_one_repository(
        self, factory: InMemoryUnitOfWorkFactory, clock: FrozenClock, metrics
    ) -> None:
        """A dedicated worker can serve one large repository."""
        enqueue(factory, make_job())
        runner = build_runner(
            factory, clock, metrics, {JobKind.INGEST_COMMIT: lambda job: None}
        )
        assert runner.run_once(repository_id=RepositoryId.generate()) is None
        assert runner.run_once(repository_id=REPOSITORY) is not None

    def test_honours_backoff_by_not_claiming_unavailable_work(
        self, factory: InMemoryUnitOfWorkFactory, clock: FrozenClock, metrics
    ) -> None:
        """A job in backoff is skipped without the worker sleeping."""
        enqueue(factory, make_job(available_at=NOW + timedelta(minutes=5)))
        runner = build_runner(
            factory, clock, metrics, {JobKind.INGEST_COMMIT: lambda job: None}
        )
        assert runner.run_once() is None
        clock.advance(600)
        assert runner.run_once() is not None


class TestFailure:
    """Retry, dead-lettering and error classification."""

    def make_failing_runner(self, factory, clock, metrics, error: Exception):
        """Build a runner whose handler always raises.

        Args:
            error: Exception the handler raises.
        """

        def handler(job: Job) -> None:
            raise error

        return build_runner(factory, clock, metrics, {JobKind.INGEST_COMMIT: handler})

    def test_a_failure_requeues_with_backoff(
        self, factory: InMemoryUnitOfWorkFactory, clock: FrozenClock, metrics
    ) -> None:
        """A recoverable failure returns the job to the queue, later."""
        enqueue(
            factory,
            make_job(
                retry_policy=RetryPolicy(
                    base_delay_seconds=10, multiplier=1, jitter_ratio=0
                )
            ),
        )
        outcome = self.make_failing_runner(
            factory, clock, metrics, RuntimeError("boom")
        ).run_once()
        assert outcome is not None
        assert outcome.succeeded is False
        assert outcome.will_retry is True
        assert outcome.job.state is JobState.QUEUED
        assert outcome.retry_after == NOW + timedelta(seconds=10)

    def test_the_failure_reason_is_recorded(
        self, factory: InMemoryUnitOfWorkFactory, clock: FrozenClock, metrics
    ) -> None:
        """The stored job names the exception type and message."""
        enqueue(factory, make_job())
        outcome = self.make_failing_runner(
            factory, clock, metrics, RuntimeError("clone timed out")
        ).run_once()
        assert "RuntimeError" in outcome.job.last_error
        assert "clone timed out" in outcome.job.last_error

    def test_exhausting_attempts_dead_letters(
        self, factory: InMemoryUnitOfWorkFactory, clock: FrozenClock, metrics
    ) -> None:
        """A job that keeps failing stops rather than cycling forever."""
        enqueue(factory, make_job(retry_policy=RetryPolicy(max_attempts=1)))
        outcome = self.make_failing_runner(
            factory, clock, metrics, RuntimeError("boom")
        ).run_once()
        assert outcome.will_retry is False
        assert outcome.is_dead is True
        assert outcome.job.state is JobState.DEAD
        assert outcome.job.last_error is not None

    def test_retries_until_the_ceiling_then_dies(
        self, factory: InMemoryUnitOfWorkFactory, clock: FrozenClock, metrics
    ) -> None:
        """The attempt ceiling is honoured across successive leases."""
        enqueue(
            factory,
            make_job(
                retry_policy=RetryPolicy(
                    max_attempts=3, base_delay_seconds=1, multiplier=1, jitter_ratio=0
                )
            ),
        )
        runner = self.make_failing_runner(factory, clock, metrics, RuntimeError("boom"))
        states = []
        for _ in range(3):
            outcome = runner.run_once()
            states.append(outcome.job.state)
            clock.advance(60)
        assert states == [JobState.QUEUED, JobState.QUEUED, JobState.DEAD]
        assert runner.run_once() is None

    def test_a_non_retryable_domain_error_dies_immediately(
        self, factory: InMemoryUnitOfWorkFactory, clock: FrozenClock, metrics
    ) -> None:
        """An error that declares itself permanent is not retried.

        Retrying a malformed payload or a withdrawn repository burns the whole attempt
        budget on a fault that cannot resolve itself.
        """
        enqueue(factory, make_job(retry_policy=RetryPolicy(max_attempts=5)))
        outcome = self.make_failing_runner(
            factory, clock, metrics, PermanentError("payload is malformed")
        ).run_once()
        assert outcome.will_retry is False
        assert outcome.job.state is JobState.DEAD
        assert outcome.job.attempts == 1

    def test_a_retryable_domain_error_is_retried(
        self, factory: InMemoryUnitOfWorkFactory, clock: FrozenClock, metrics
    ) -> None:
        """An infrastructure error that declares itself transient is retried."""
        enqueue(factory, make_job())
        outcome = self.make_failing_runner(
            factory, clock, metrics, GitCommandError(["git", "fetch"], 128, "network")
        ).run_once()
        assert outcome.will_retry is True

    def test_an_unexpected_exception_is_treated_as_retryable(
        self, factory: InMemoryUnitOfWorkFactory, clock: FrozenClock, metrics
    ) -> None:
        """An unclassified fault is assumed transient, bounded by the attempt ceiling.

        A transient fault we failed to classify is likelier than a permanent one, and
        the ceiling bounds the cost of being wrong.
        """
        enqueue(factory, make_job())
        outcome = self.make_failing_runner(
            factory, clock, metrics, KeyError("unexpected")
        ).run_once()
        assert outcome.will_retry is True

    def test_a_missing_handler_dead_letters_without_retrying(
        self, factory: InMemoryUnitOfWorkFactory, clock: FrozenClock, metrics
    ) -> None:
        """A job no worker can run fails visibly instead of stalling the queue.

        Left queued, it would be leased and released forever with no error anywhere,
        which is exactly the silent degradation PRD principle P11 forbids.
        """
        enqueue(factory, make_job(kind=JobKind.INGEST_COMMIT))
        runner = build_runner(
            factory,
            clock,
            metrics,
            {JobKind.INGEST_COMMIT: lambda job: None, JobKind.DISCOVER_COMMITS: None},
        )
        # Replace the registry so the leased kind has no callable behind it.
        runner._handlers = {JobKind.INGEST_COMMIT: None}  # type: ignore[attr-defined]
        outcome = runner.run_once()
        assert outcome.job.state is JobState.DEAD
        assert "no handler is registered" in outcome.error

    def test_the_failure_is_persisted(
        self, factory: InMemoryUnitOfWorkFactory, clock: FrozenClock, metrics
    ) -> None:
        """The stored job reflects the outcome, not just the returned value."""
        job = enqueue(factory, make_job(retry_policy=RetryPolicy(max_attempts=1)))
        self.make_failing_runner(
            factory, clock, metrics, RuntimeError("boom")
        ).run_once()
        with factory() as unit_of_work:
            stored = unit_of_work.jobs.get(job.job_id)
        assert stored.state is JobState.DEAD


class TestDrain:
    """Executing until the queue empties."""

    def test_executes_every_available_job(
        self, factory: InMemoryUnitOfWorkFactory, clock: FrozenClock, metrics
    ) -> None:
        """Draining runs the whole queue."""
        for _ in range(3):
            enqueue(factory, make_job())
        runner = build_runner(
            factory, clock, metrics, {JobKind.INGEST_COMMIT: lambda job: None}
        )
        assert len(runner.drain(limit=10)) == 3

    def test_stops_at_the_limit(
        self, factory: InMemoryUnitOfWorkFactory, clock: FrozenClock, metrics
    ) -> None:
        """The bound is mandatory because a handler may enqueue further work.

        Commit discovery enqueues one ingestion job per commit, so an unbounded drain
        could run for the lifetime of the repository with no chance to stop it.
        """
        for _ in range(5):
            enqueue(factory, make_job())
        runner = build_runner(
            factory, clock, metrics, {JobKind.INGEST_COMMIT: lambda job: None}
        )
        assert len(runner.drain(limit=2)) == 2

    def test_rejects_a_non_positive_limit(
        self, factory: InMemoryUnitOfWorkFactory, clock: FrozenClock, metrics
    ) -> None:
        """A zero bound would silently do nothing."""
        runner = build_runner(factory, clock, metrics, {})
        with pytest.raises(ValueError, match="limit"):
            runner.drain(limit=0)

    def test_continues_past_a_failing_job(
        self, factory: InMemoryUnitOfWorkFactory, clock: FrozenClock, metrics
    ) -> None:
        """One poisonous job does not stop the drain."""
        enqueue(factory, make_job(idempotency_key="bad", payload={"fail": "yes"}))
        enqueue(factory, make_job(idempotency_key="good"))

        def handler(job: Job) -> None:
            if job.payload.get("fail"):
                raise RuntimeError("boom")

        runner = build_runner(factory, clock, metrics, {JobKind.INGEST_COMMIT: handler})
        outcomes = runner.drain(limit=10)
        assert sorted(outcome.succeeded for outcome in outcomes) == [False, True]


class TestReclamation:
    """Recovering work from dead workers."""

    def test_reclaims_an_expired_lease(
        self, factory: InMemoryUnitOfWorkFactory, clock: FrozenClock, metrics
    ) -> None:
        """A worker that dies holding a lease costs one lease duration, not the job.

        Without the sweep the job stays claimed forever and the pipeline stalls with
        no error recorded anywhere.
        """
        enqueue(factory, make_job(retry_policy=RetryPolicy(max_attempts=5)))
        runner = build_runner(
            factory,
            clock,
            metrics,
            {JobKind.INGEST_COMMIT: lambda job: None},
            lease_duration=timedelta(minutes=1),
        )
        with factory() as unit_of_work:
            leased = unit_of_work.jobs.lease_next(
                owner="dead-worker", now=clock.now(), duration=timedelta(minutes=1)
            )
            unit_of_work.commit()
        assert leased.state is JobState.LEASED

        clock.advance(120)
        reclaimed = runner.reclaim_expired()
        assert [job.state for job in reclaimed] == [JobState.QUEUED]

    def test_does_not_reclaim_a_live_lease(
        self, factory: InMemoryUnitOfWorkFactory, clock: FrozenClock, metrics
    ) -> None:
        """A working worker is left alone."""
        enqueue(factory, make_job())
        runner = build_runner(
            factory, clock, metrics, {JobKind.INGEST_COMMIT: lambda job: None}
        )
        with factory() as unit_of_work:
            unit_of_work.jobs.lease_next(
                owner="busy", now=clock.now(), duration=timedelta(hours=1)
            )
            unit_of_work.commit()
        clock.advance(60)
        assert runner.reclaim_expired() == ()

    def test_a_reclaimed_job_with_no_attempts_left_dies(
        self, factory: InMemoryUnitOfWorkFactory, clock: FrozenClock, metrics
    ) -> None:
        """A job that repeatedly kills its worker stops rather than looping.

        Requeueing unconditionally would turn one poisonous job into an unbounded
        loop consuming a worker every lease period.
        """
        enqueue(factory, make_job(retry_policy=RetryPolicy(max_attempts=1)))
        runner = build_runner(
            factory, clock, metrics, {JobKind.INGEST_COMMIT: lambda job: None}
        )
        with factory() as unit_of_work:
            unit_of_work.jobs.lease_next(
                owner="dead", now=clock.now(), duration=timedelta(minutes=1)
            )
            unit_of_work.commit()
        clock.advance(120)
        assert [job.state for job in runner.reclaim_expired()] == [JobState.DEAD]

    def test_a_reclaimed_job_can_be_leased_again(
        self, factory: InMemoryUnitOfWorkFactory, clock: FrozenClock, metrics
    ) -> None:
        """Reclamation actually returns the work to circulation."""
        enqueue(factory, make_job(retry_policy=RetryPolicy(max_attempts=5)))
        runner = build_runner(
            factory, clock, metrics, {JobKind.INGEST_COMMIT: lambda job: None}
        )
        with factory() as unit_of_work:
            unit_of_work.jobs.lease_next(
                owner="dead", now=clock.now(), duration=timedelta(minutes=1)
            )
            unit_of_work.commit()
        clock.advance(120)
        runner.reclaim_expired()
        assert runner.run_once() is not None


class TestObservability:
    """Metrics the runner publishes."""

    def test_counts_leases_and_completions(
        self, factory: InMemoryUnitOfWorkFactory, clock: FrozenClock, metrics
    ) -> None:
        """Leases and outcomes are separately observable per kind."""
        enqueue(factory, make_job())
        build_runner(
            factory, clock, metrics, {JobKind.INGEST_COMMIT: lambda job: None}
        ).run_once()
        assert (
            metrics.counter_value("ria_jobs_leased_total", {"kind": "ingest_commit"})
            == 1
        )
        assert (
            metrics.counter_value(
                "ria_jobs_completed_total",
                {"kind": "ingest_commit", "outcome": "succeeded"},
            )
            == 1
        )

    def test_distinguishes_retry_from_death(
        self, factory: InMemoryUnitOfWorkFactory, clock: FrozenClock, metrics
    ) -> None:
        """An operator can tell a transient wobble from an exhausted job."""
        enqueue(factory, make_job(retry_policy=RetryPolicy(max_attempts=1)))

        def handler(job: Job) -> None:
            raise RuntimeError("boom")

        build_runner(
            factory, clock, metrics, {JobKind.INGEST_COMMIT: handler}
        ).run_once()
        assert (
            metrics.counter_value(
                "ria_jobs_completed_total",
                {"kind": "ingest_commit", "outcome": "dead"},
            )
            == 1
        )

    def test_times_the_handler(
        self, factory: InMemoryUnitOfWorkFactory, clock: FrozenClock, metrics
    ) -> None:
        """Handler runtime is measured per kind and per outcome."""
        enqueue(factory, make_job())
        build_runner(
            factory, clock, metrics, {JobKind.INGEST_COMMIT: lambda job: None}
        ).run_once()
        assert (
            metrics.distribution(
                "ria_job_handler_seconds",
                {"kind": "ingest_commit", "outcome": "success"},
            )
            is not None
        )

    def test_publishes_queue_depth_for_every_state(
        self, factory: InMemoryUnitOfWorkFactory, clock: FrozenClock, metrics
    ) -> None:
        """Depth is gauged for every state, including empty ones.

        Reporting only non-empty states would leave a stale gauge behind when a state
        drains to zero, and an autoscaler would keep acting on it.
        """
        enqueue(factory, make_job())
        runner = build_runner(
            factory, clock, metrics, {JobKind.INGEST_COMMIT: lambda job: None}
        )
        depth = runner.report_queue_depth()
        assert depth == {"queued": 1}
        assert metrics.gauge_value("ria_job_queue_depth", {"state": "queued"}) == 1
        assert metrics.gauge_value("ria_job_queue_depth", {"state": "dead"}) == 0

    def test_duration_is_never_negative_under_a_frozen_clock(
        self, factory: InMemoryUnitOfWorkFactory, clock: FrozenClock, metrics
    ) -> None:
        """A frozen clock yields zero, not a negative duration.

        A negative observation would violate the metrics contract and corrupt every
        aggregate computed from the series.
        """
        enqueue(factory, make_job())
        outcome = build_runner(
            factory, clock, metrics, {JobKind.INGEST_COMMIT: lambda job: None}
        ).run_once()
        assert outcome.duration_seconds >= 0.0


class TestJitterRobustness:
    """Behaviour when the injected randomness misbehaves."""

    @pytest.mark.parametrize("value", [-5.0, 5.0, float("nan")])
    def test_out_of_range_randomness_does_not_break_the_retry_path(
        self,
        factory: InMemoryUnitOfWorkFactory,
        clock: FrozenClock,
        metrics,
        value: float,
    ) -> None:
        """Jitter is clamped rather than trusted.

        An out-of-range value would otherwise raise inside the retry path, converting a
        recoverable handler failure into an unrecoverable runner failure.
        """
        enqueue(factory, make_job())

        def handler(job: Job) -> None:
            raise RuntimeError("boom")

        runner = build_runner(
            factory,
            clock,
            metrics,
            {JobKind.INGEST_COMMIT: handler},
            random_source=lambda: value,
        )
        outcome = runner.run_once()
        assert outcome.will_retry is True

    def test_a_raising_random_source_does_not_break_the_retry_path(
        self, factory: InMemoryUnitOfWorkFactory, clock: FrozenClock, metrics
    ) -> None:
        """A broken randomness source falls back to the undithered delay."""
        enqueue(factory, make_job())

        def handler(job: Job) -> None:
            raise RuntimeError("boom")

        def broken() -> float:
            raise OSError("entropy unavailable")

        runner = build_runner(
            factory,
            clock,
            metrics,
            {JobKind.INGEST_COMMIT: handler},
            random_source=broken,
        )
        assert runner.run_once().will_retry is True
