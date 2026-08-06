"""Integration tests for the SQLite job queue.

Three of the queue's guarantees are delegated to the database and are therefore only
observable here: the unique index that makes enqueue idempotent under concurrency, the
check constraints that stop a lease becoming unreclaimable, and the cascade that
removes a purged repository's work.
"""

from __future__ import annotations

import sqlite3
from datetime import timedelta

import pytest

from ria.container import Container
from ria.domain.enums import JobKind, JobState
from ria.domain.errors import JobNotFoundError, StorageError
from ria.domain.identity import Moniker, RepositoryId
from ria.domain.models.job import Job, JobId, RetryPolicy
from ria.domain.models.repository import Repository
from tests.ria.conftest import utc

NOW = utc(2026, 1, 1, 12)
LEASE = timedelta(minutes=30)


def make_repository(owner: str = "acme") -> Repository:
    """Build a repository to own the jobs under test.

    Args:
        owner: Owner component, so several repositories can coexist.
    """
    return Repository(
        repository_id=RepositoryId.generate(),
        moniker=Moniker.for_repository(host="github.com", owner=owner, name="widgets"),
        origin_url=f"https://github.com/{owner}/widgets.git",
        default_branch="main",
        tenant_id="tenant-a",
        registered_at=NOW,
        updated_at=NOW,
    )


def make_job(repository_id: RepositoryId, **overrides) -> Job:
    """Build a queued job.

    Args:
        repository_id: Owning repository.
        **overrides: Fields to replace.
    """
    defaults = dict(
        job_id=JobId.generate(),
        repository_id=repository_id,
        kind=JobKind.INGEST_COMMIT,
        idempotency_key=f"ingest:{JobId.generate()}",
        created_at=NOW,
        updated_at=NOW,
        available_at=NOW,
        payload={"sha": "a" * 40},
    )
    defaults.update(overrides)
    return Job(**defaults)


@pytest.fixture
def repository(container: Container) -> Repository:
    """A registered repository, committed."""
    record = make_repository()
    with container.unit_of_work_factory() as unit_of_work:
        unit_of_work.repositories.add(record)
        unit_of_work.commit()
    return record


def enqueue(container: Container, job: Job) -> Job:
    """Enqueue a job through a committed transaction."""
    with container.unit_of_work_factory() as unit_of_work:
        stored = unit_of_work.jobs.enqueue(job)
        unit_of_work.commit()
    return stored


class TestEnqueue:
    """Insertion and idempotency."""

    def test_round_trips_every_field(self, container: Container, repository) -> None:
        """A job survives storage including its policy and payload.

        The retry policy and payload are stored as JSON documents, so the round trip
        is the only proof the mapping is lossless.
        """
        job = make_job(
            repository.repository_id,
            priority=-5,
            payload={"sha": "a" * 40, "reason": "manual"},
            retry_policy=RetryPolicy(max_attempts=7, base_delay_seconds=1.5),
            stage="enumerate",
        )
        enqueue(container, job)
        with container.unit_of_work_factory() as unit_of_work:
            loaded = unit_of_work.jobs.get(job.job_id)
        assert loaded == job
        assert loaded.retry_policy.max_attempts == 7
        assert loaded.payload["reason"] == "manual"
        assert loaded.stage == "enumerate"

    def test_is_idempotent_on_the_key(self, container: Container, repository) -> None:
        """A second enqueue of one key returns the existing job.

        This is what makes commit discovery safe to re-run: a second pass over an
        already-queued range performs no writes.
        """
        first = enqueue(
            container, make_job(repository.repository_id, idempotency_key="ingest:abc")
        )
        second = enqueue(
            container, make_job(repository.repository_id, idempotency_key="ingest:abc")
        )
        assert second.job_id == first.job_id
        with container.unit_of_work_factory() as unit_of_work:
            assert unit_of_work.jobs.count_by_state(repository.repository_id) == {
                "queued": 1
            }

    def test_idempotency_is_scoped_per_repository(self, container: Container) -> None:
        """Two repositories may use the same key without colliding.

        Discovery derives its keys from a commit SHA, and two forks legitimately share
        object names.
        """
        first = make_repository("first")
        second = make_repository("second")
        with container.unit_of_work_factory() as unit_of_work:
            unit_of_work.repositories.add(first)
            unit_of_work.repositories.add(second)
            unit_of_work.commit()
        a = enqueue(container, make_job(first.repository_id, idempotency_key="shared"))
        b = enqueue(container, make_job(second.repository_id, idempotency_key="shared"))
        assert a.job_id != b.job_id

    def test_idempotency_is_enforced_by_the_database(
        self, container: Container, repository
    ) -> None:
        """A unique index, not a read-then-write, guards the key.

        A check followed by an insert is not atomic, so two workers enqueueing one key
        simultaneously would both pass the check.
        """
        with container.unit_of_work_factory() as unit_of_work:
            rows = unit_of_work.repositories  # keep the scope open
            assert rows is not None
            connection = container.connections.connection()
            indexes = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND tbl_name='ria_job'"
            ).fetchall()
        assert "ux_ria_job_idempotency" in {row["name"] for row in indexes}

    def test_requires_a_registered_repository(self, container: Container) -> None:
        """A job cannot be orphaned from its repository."""
        with pytest.raises(StorageError):
            with container.unit_of_work_factory() as unit_of_work:
                unit_of_work.jobs.enqueue(make_job(RepositoryId.generate()))


class TestClaim:
    """Leasing."""

    def test_claims_an_available_job(self, container: Container, repository) -> None:
        """A claim records the owner, the deadline and the attempt."""
        enqueue(container, make_job(repository.repository_id))
        with container.unit_of_work_factory() as unit_of_work:
            leased = unit_of_work.jobs.lease_next(
                owner="worker-1", now=NOW, duration=LEASE
            )
            unit_of_work.commit()
        assert leased is not None
        assert leased.state is JobState.LEASED
        assert leased.lease_owner == "worker-1"
        assert leased.attempts == 1

    def test_a_claimed_job_is_not_claimed_again(
        self, container: Container, repository
    ) -> None:
        """Two workers never receive one job."""
        enqueue(container, make_job(repository.repository_id))
        with container.unit_of_work_factory() as unit_of_work:
            unit_of_work.jobs.lease_next(owner="worker-1", now=NOW, duration=LEASE)
            unit_of_work.commit()
        with container.unit_of_work_factory() as unit_of_work:
            assert (
                unit_of_work.jobs.lease_next(owner="worker-2", now=NOW, duration=LEASE)
                is None
            )

    def test_skips_a_job_in_backoff(self, container: Container, repository) -> None:
        """Availability enforces retry backoff without a worker sleeping."""
        enqueue(
            container,
            make_job(
                repository.repository_id, available_at=NOW + timedelta(minutes=10)
            ),
        )
        with container.unit_of_work_factory() as unit_of_work:
            assert (
                unit_of_work.jobs.lease_next(owner="w", now=NOW, duration=LEASE) is None
            )
            assert (
                unit_of_work.jobs.lease_next(
                    owner="w", now=NOW + timedelta(minutes=11), duration=LEASE
                )
                is not None
            )
            unit_of_work.commit()

    def test_claims_in_priority_then_age_order(
        self, container: Container, repository
    ) -> None:
        """Lower priority values are claimed first, then older jobs.

        The third sort key makes the order total, so two equally urgent jobs are
        claimed in enqueue order rather than in whatever order the engine returns.
        """
        urgent = enqueue(
            container,
            make_job(repository.repository_id, priority=-10, idempotency_key="urgent"),
        )
        normal = enqueue(
            container, make_job(repository.repository_id, idempotency_key="normal")
        )
        with container.unit_of_work_factory() as unit_of_work:
            first = unit_of_work.jobs.lease_next(owner="w", now=NOW, duration=LEASE)
            second = unit_of_work.jobs.lease_next(owner="w", now=NOW, duration=LEASE)
            unit_of_work.commit()
        assert first.job_id == urgent.job_id
        assert second.job_id == normal.job_id

    def test_filters_by_kind(self, container: Container, repository) -> None:
        """A dedicated worker claims only the kinds it can run."""
        enqueue(
            container,
            make_job(repository.repository_id, kind=JobKind.DISCOVER_COMMITS),
        )
        with container.unit_of_work_factory() as unit_of_work:
            assert (
                unit_of_work.jobs.lease_next(
                    owner="w", now=NOW, duration=LEASE, kinds=(JobKind.INGEST_COMMIT,)
                )
                is None
            )
            assert (
                unit_of_work.jobs.lease_next(
                    owner="w",
                    now=NOW,
                    duration=LEASE,
                    kinds=(JobKind.DISCOVER_COMMITS,),
                )
                is not None
            )
            unit_of_work.commit()

    def test_filters_by_repository(self, container: Container) -> None:
        """Work can be scoped to one repository."""
        first = make_repository("first")
        second = make_repository("second")
        with container.unit_of_work_factory() as unit_of_work:
            unit_of_work.repositories.add(first)
            unit_of_work.repositories.add(second)
            unit_of_work.commit()
        enqueue(container, make_job(second.repository_id))
        with container.unit_of_work_factory() as unit_of_work:
            assert (
                unit_of_work.jobs.lease_next(
                    owner="w",
                    now=NOW,
                    duration=LEASE,
                    repository_id=first.repository_id,
                )
                is None
            )
            unit_of_work.commit()

    def test_an_uncommitted_claim_is_rolled_back(
        self, container: Container, repository
    ) -> None:
        """A claim abandoned without committing leaves the job available.

        This is what makes the claim safe: a worker that dies between claiming and
        committing has claimed nothing.
        """
        enqueue(container, make_job(repository.repository_id))
        with container.unit_of_work_factory() as unit_of_work:
            unit_of_work.jobs.lease_next(owner="w", now=NOW, duration=LEASE)
        with container.unit_of_work_factory() as unit_of_work:
            assert (
                unit_of_work.jobs.lease_next(owner="w2", now=NOW, duration=LEASE)
                is not None
            )
            unit_of_work.commit()


class TestPersistence:
    """Updating and reading jobs."""

    def test_save_persists_a_transition(self, container: Container, repository) -> None:
        """A completed job is stored in its terminal state."""
        job = enqueue(container, make_job(repository.repository_id))
        with container.unit_of_work_factory() as unit_of_work:
            leased = unit_of_work.jobs.lease_next(owner="w", now=NOW, duration=LEASE)
            unit_of_work.jobs.save(leased.succeeded(now=NOW))
            unit_of_work.commit()
        with container.unit_of_work_factory() as unit_of_work:
            assert unit_of_work.jobs.get(job.job_id).state is JobState.SUCCEEDED

    def test_save_raises_for_an_absent_job(
        self, container: Container, repository
    ) -> None:
        """Updating an unrecorded job raises rather than inserting."""
        with pytest.raises(JobNotFoundError):
            with container.unit_of_work_factory() as unit_of_work:
                unit_of_work.jobs.save(make_job(repository.repository_id))

    def test_find_by_key(self, container: Container, repository) -> None:
        """A job is addressable by its idempotency key."""
        job = enqueue(
            container, make_job(repository.repository_id, idempotency_key="ingest:xyz")
        )
        with container.unit_of_work_factory() as unit_of_work:
            found = unit_of_work.jobs.find_by_key(
                repository.repository_id, "ingest:xyz"
            )
        assert found.job_id == job.job_id

    def test_counts_and_lists_by_state(self, container: Container, repository) -> None:
        """Queue depth is reportable per state, omitting empty states."""
        enqueue(container, make_job(repository.repository_id, idempotency_key="a"))
        enqueue(container, make_job(repository.repository_id, idempotency_key="b"))
        with container.unit_of_work_factory() as unit_of_work:
            unit_of_work.jobs.lease_next(owner="w", now=NOW, duration=LEASE)
            unit_of_work.commit()
        with container.unit_of_work_factory() as unit_of_work:
            counts = unit_of_work.jobs.count_by_state(repository.repository_id)
            queued = unit_of_work.jobs.list_by_state(JobState.QUEUED)
        assert counts == {"queued": 1, "leased": 1}
        assert len(queued) == 1

    def test_list_rejects_a_negative_limit(self, container: Container) -> None:
        """A nonsensical limit is rejected rather than passed to SQL."""
        with container.unit_of_work_factory() as unit_of_work:
            with pytest.raises(ValueError):
                unit_of_work.jobs.list_by_state(JobState.QUEUED, limit=-1)


class TestExpirySweep:
    """Reclaiming lapsed leases."""

    def test_reclaims_an_expired_lease(self, container: Container, repository) -> None:
        """A dead worker's job returns to the queue."""
        enqueue(
            container,
            make_job(
                repository.repository_id, retry_policy=RetryPolicy(max_attempts=5)
            ),
        )
        with container.unit_of_work_factory() as unit_of_work:
            unit_of_work.jobs.lease_next(
                owner="dead", now=NOW, duration=timedelta(minutes=1)
            )
            unit_of_work.commit()
        with container.unit_of_work_factory() as unit_of_work:
            reclaimed = unit_of_work.jobs.requeue_expired(
                now=NOW + timedelta(minutes=5)
            )
            unit_of_work.commit()
        assert [job.state for job in reclaimed] == [JobState.QUEUED]

    def test_leaves_a_live_lease_alone(self, container: Container, repository) -> None:
        """A working worker is not interrupted."""
        enqueue(container, make_job(repository.repository_id))
        with container.unit_of_work_factory() as unit_of_work:
            unit_of_work.jobs.lease_next(
                owner="busy", now=NOW, duration=timedelta(hours=2)
            )
            unit_of_work.commit()
        with container.unit_of_work_factory() as unit_of_work:
            assert (
                unit_of_work.jobs.requeue_expired(now=NOW + timedelta(minutes=5)) == ()
            )

    def test_a_lease_always_has_a_deadline(
        self, container: Container, repository
    ) -> None:
        """The database refuses a lease with no expiry.

        A lease with no deadline would never be reclaimed, so its job would stall the
        queue forever with nothing to detect it.
        """
        enqueue(container, make_job(repository.repository_id))
        connection = container.connections.connection()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE ria_job SET state = 'leased', lease_owner = 'w', "
                "leased_until = NULL"
            )

    def test_a_dead_job_must_state_a_reason(
        self, container: Container, repository
    ) -> None:
        """The database enforces the same invariant as the entity."""
        enqueue(container, make_job(repository.repository_id))
        connection = container.connections.connection()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE ria_job SET state = 'dead', last_error = NULL")


class TestCancellation:
    """Withdrawing queued work."""

    def test_cancels_incomplete_work(self, container: Container, repository) -> None:
        """Pausing a repository stops work that has not finished."""
        enqueue(container, make_job(repository.repository_id, idempotency_key="a"))
        enqueue(container, make_job(repository.repository_id, idempotency_key="b"))
        with container.unit_of_work_factory() as unit_of_work:
            cancelled = unit_of_work.jobs.cancel_pending(
                repository.repository_id, now=NOW
            )
            unit_of_work.commit()
        assert cancelled == 2
        with container.unit_of_work_factory() as unit_of_work:
            assert unit_of_work.jobs.count_by_state(repository.repository_id) == {
                "cancelled": 2
            }

    def test_leaves_completed_work_alone(
        self, container: Container, repository
    ) -> None:
        """Cancelling a succeeded job would rewrite the record of work that ran."""
        enqueue(container, make_job(repository.repository_id))
        with container.unit_of_work_factory() as unit_of_work:
            leased = unit_of_work.jobs.lease_next(owner="w", now=NOW, duration=LEASE)
            unit_of_work.jobs.save(leased.succeeded(now=NOW))
            unit_of_work.commit()
        with container.unit_of_work_factory() as unit_of_work:
            assert (
                unit_of_work.jobs.cancel_pending(repository.repository_id, now=NOW) == 0
            )


class TestCascade:
    """Removal with the owning repository."""

    def test_purging_a_repository_removes_its_jobs(
        self, container: Container, repository
    ) -> None:
        """Queued work does not outlive the repository it concerns."""
        enqueue(container, make_job(repository.repository_id))
        with container.unit_of_work_factory() as unit_of_work:
            unit_of_work.repositories.delete(repository.repository_id)
            unit_of_work.commit()
        with container.unit_of_work_factory() as unit_of_work:
            assert unit_of_work.jobs.count_by_state(repository.repository_id) == {}

    def test_explicit_deletion_reports_a_count(
        self, container: Container, repository
    ) -> None:
        """Deleting a repository's jobs directly reports how many went."""
        enqueue(container, make_job(repository.repository_id, idempotency_key="a"))
        enqueue(container, make_job(repository.repository_id, idempotency_key="b"))
        with container.unit_of_work_factory() as unit_of_work:
            assert unit_of_work.jobs.delete_by_repository(repository.repository_id) == 2
            unit_of_work.commit()
