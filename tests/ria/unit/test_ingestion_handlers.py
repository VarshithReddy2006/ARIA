"""Tests for the ingestion job handlers.

The handlers are thin, and the two things they must get right are exactly the two
things a thin adapter usually gets wrong: reading the payload strictly, and refusing to
act on a repository an operator has withdrawn.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from ria.application.ingestion_handlers import (
    PAYLOAD_LIMIT,
    PAYLOAD_REF,
    PAYLOAD_SHA,
    IngestionHandlers,
    build_ingestion_handlers,
)
from ria.application.repository_manager import (
    RegisterRepositoryCommand,
    RepositoryManager,
)
from ria.domain.enums import JobKind, RepositoryStatus
from ria.domain.errors import ApplicationError, RepositoryNotFoundError
from ria.domain.identity import RepositoryId
from ria.domain.models.job import Job, JobId
from ria.domain.models.repository import Repository
from ria.observability.metrics import InMemoryMetricsSink
from tests.ria.conftest import utc
from tests.ria.fakes import FrozenClock, InMemoryUnitOfWorkFactory

NOW = utc(2026, 1, 1, 12)
MIRROR = Path("/mirrors/acme_widgets")


class RecordingMirrorManager:
    """Mirror manager double recording what it was asked to do."""

    def __init__(self, *, present: bool = True) -> None:
        self.present = present
        self.acquired: List[str] = []
        self.required: List[str] = []

    def acquire(self, repository: Repository, *, refresh: bool = True):
        """Record an acquisition and report a clone."""
        self.acquired.append(repository.slug)
        return _MirrorState(path=MIRROR, was_cloned=True, was_fetched=False)

    def require(self, moniker) -> Path:
        """Return the mirror path, or raise when no mirror is present."""
        self.required.append(str(moniker))
        if not self.present:
            raise ApplicationError("mirror is absent", {"moniker": str(moniker)})
        return MIRROR


class _MirrorState:
    """Minimal stand-in for the mirror manager's result object."""

    def __init__(self, *, path: Path, was_cloned: bool, was_fetched: bool) -> None:
        self.path = path
        self.was_cloned = was_cloned
        self.was_fetched = was_fetched


class RecordingDiscovery:
    """Commit discovery double capturing its keyword arguments."""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def discover(self, repository: Repository, mirror_path: Path, **kwargs: Any) -> str:
        """Record the call and report a trivial result."""
        self.calls.append(
            {"repository": repository.slug, "path": mirror_path, **kwargs}
        )
        return "discovered"


class RecordingIngestion:
    """Ingestion service double capturing the ref it was asked to build."""

    def __init__(self, *, already_indexed: bool = False) -> None:
        self.already_indexed = already_indexed
        self.calls: List[Dict[str, Any]] = []

    def ingest_commit(
        self,
        repository: Repository,
        ref: str,
        *,
        job_id: Optional[str] = None,
        force: bool = False,
    ):
        """Record the call and report an outcome."""
        self.calls.append({"repository": repository.slug, "ref": ref, "job_id": job_id})
        return _IngestionOutcome(self.already_indexed)


class _IngestionOutcome:
    """Minimal stand-in for the ingestion service's result object."""

    def __init__(self, was_already_indexed: bool) -> None:
        self.was_already_indexed = was_already_indexed


@pytest.fixture
def context(clock: FrozenClock, metrics: InMemoryMetricsSink):
    """Assemble handlers over fakes, with a registered repository."""
    factory = InMemoryUnitOfWorkFactory()
    manager = RepositoryManager(factory, clock, metrics)
    repository = manager.register(
        RegisterRepositoryCommand(origin_url="https://github.com/acme/widgets.git")
    )
    mirrors = RecordingMirrorManager()
    discovery = RecordingDiscovery()
    ingestion = RecordingIngestion()
    handlers = IngestionHandlers(manager, mirrors, discovery, ingestion, metrics)
    return {
        "factory": factory,
        "manager": manager,
        "repository": repository,
        "mirrors": mirrors,
        "discovery": discovery,
        "ingestion": ingestion,
        "handlers": handlers,
    }


def make_job(repository_id: RepositoryId, kind: JobKind, payload=None) -> Job:
    """Build a leased-shaped job for a handler.

    Args:
        repository_id: Owning repository.
        kind: Job kind.
        payload: Job payload.
    """
    return Job(
        job_id=JobId.generate(),
        repository_id=repository_id,
        kind=kind,
        idempotency_key=f"{kind.value}:key",
        created_at=NOW,
        updated_at=NOW,
        available_at=NOW,
        payload=payload or {},
    )


class TestRegistry:
    """The handler mapping."""

    def test_covers_every_job_kind(self, context) -> None:
        """No kind is left without a handler.

        A kind absent from the mapping is dead-lettered by the runner, so an
        incomplete registry silently stops a whole class of work.
        """
        mapping = context["handlers"].as_mapping()
        assert set(mapping) == set(JobKind)

    def test_builder_produces_the_same_mapping(self, context, metrics) -> None:
        """The convenience builder wires the same handlers."""
        mapping = build_ingestion_handlers(
            context["manager"],
            context["mirrors"],
            context["discovery"],
            context["ingestion"],
            metrics,
        )
        assert set(mapping) == set(JobKind)


class TestAcquireRepository:
    """The mirror acquisition handler."""

    def test_acquires_the_mirror(self, context) -> None:
        """Acquisition refreshes the mirror for the job's repository."""
        job = make_job(context["repository"].repository_id, JobKind.ACQUIRE_REPOSITORY)
        context["handlers"].acquire_repository(job)
        assert context["mirrors"].acquired == ["acme/widgets"]

    def test_counts_the_outcome(self, context, metrics) -> None:
        """A clone is distinguishable from a fetch in metrics."""
        job = make_job(context["repository"].repository_id, JobKind.ACQUIRE_REPOSITORY)
        context["handlers"].acquire_repository(job)
        assert (
            metrics.counter_value(
                "ria_ingestion_jobs_handled_total",
                {"kind": "acquire_repository", "outcome": "cloned"},
            )
            == 1
        )


class TestDiscoverCommits:
    """The discovery handler."""

    def test_passes_the_ref_and_job_id(self, context) -> None:
        """The payload's ref reaches the service, along with the job for tracing."""
        job = make_job(
            context["repository"].repository_id,
            JobKind.DISCOVER_COMMITS,
            {PAYLOAD_REF: "main"},
        )
        context["handlers"].discover_commits(job)
        call = context["discovery"].calls[0]
        assert call["ref"] == "main"
        assert call["job_id"] == str(job.job_id)

    def test_omits_an_absent_ref(self, context) -> None:
        """Without a ref the service applies its own default."""
        job = make_job(context["repository"].repository_id, JobKind.DISCOVER_COMMITS)
        context["handlers"].discover_commits(job)
        assert context["discovery"].calls[0]["ref"] is None

    def test_forwards_a_numeric_limit(self, context) -> None:
        """A payload limit is parsed from its string form and forwarded."""
        job = make_job(
            context["repository"].repository_id,
            JobKind.DISCOVER_COMMITS,
            {PAYLOAD_LIMIT: "25"},
        )
        context["handlers"].discover_commits(job)
        assert context["discovery"].calls[0]["limit"] == 25

    def test_omits_the_limit_when_absent(self, context) -> None:
        """An absent limit is not defaulted here.

        Declaring a default in the handler would duplicate the service's own and let
        the two drift.
        """
        job = make_job(context["repository"].repository_id, JobKind.DISCOVER_COMMITS)
        context["handlers"].discover_commits(job)
        assert "limit" not in context["discovery"].calls[0]

    @pytest.mark.parametrize("value", ["abc", "", "1.5"])
    def test_rejects_a_non_integer_limit(self, context, value: str) -> None:
        """A malformed limit fails loudly rather than being ignored.

        Ignoring it would walk a different number of commits than the caller asked
        for, and the result would look like a success.
        """
        job = make_job(
            context["repository"].repository_id,
            JobKind.DISCOVER_COMMITS,
            {PAYLOAD_LIMIT: value},
        )
        with pytest.raises(ApplicationError, match="not an integer"):
            context["handlers"].discover_commits(job)

    @pytest.mark.parametrize("value", ["0", "-5"])
    def test_rejects_a_non_positive_limit(self, context, value: str) -> None:
        """A limit that walks nothing is a caller error."""
        job = make_job(
            context["repository"].repository_id,
            JobKind.DISCOVER_COMMITS,
            {PAYLOAD_LIMIT: value},
        )
        with pytest.raises(ApplicationError, match="must be positive"):
            context["handlers"].discover_commits(job)

    def test_requires_a_mirror(self, context) -> None:
        """Discovery does not clone implicitly."""
        context["mirrors"].present = False
        job = make_job(context["repository"].repository_id, JobKind.DISCOVER_COMMITS)
        with pytest.raises(ApplicationError, match="mirror is absent"):
            context["handlers"].discover_commits(job)


class TestIngestCommit:
    """The ingestion handler."""

    def test_passes_the_commit_from_the_payload(self, context) -> None:
        """The job names the commit it must build."""
        job = make_job(
            context["repository"].repository_id,
            JobKind.INGEST_COMMIT,
            {PAYLOAD_SHA: "a" * 40},
        )
        context["handlers"].ingest_commit(job)
        assert context["ingestion"].calls[0]["ref"] == "a" * 40

    def test_requires_the_commit(self, context) -> None:
        """A job with no commit is malformed and fails rather than guessing.

        Defaulting to a branch head would silently index a different commit than the
        one the job was created for.
        """
        job = make_job(context["repository"].repository_id, JobKind.INGEST_COMMIT)
        with pytest.raises(ValueError, match="missing required key 'sha'"):
            context["handlers"].ingest_commit(job)

    def test_distinguishes_a_skipped_commit(self, context, metrics, clock) -> None:
        """An already-indexed commit is counted separately from a fresh ingestion."""
        context["ingestion"].already_indexed = True
        job = make_job(
            context["repository"].repository_id,
            JobKind.INGEST_COMMIT,
            {PAYLOAD_SHA: "a" * 40},
        )
        context["handlers"].ingest_commit(job)
        assert (
            metrics.counter_value(
                "ria_ingestion_jobs_handled_total",
                {"kind": "ingest_commit", "outcome": "skipped"},
            )
            == 1
        )


class TestRepositoryGuard:
    """Refusal to act on a repository that has been withdrawn."""

    @pytest.mark.parametrize(
        "status", [RepositoryStatus.PAUSED, RepositoryStatus.ARCHIVED]
    )
    def test_refuses_a_withdrawn_repository(self, context, status) -> None:
        """Queued work does not run against a repository an operator withdrew.

        A job enqueued an hour ago would otherwise keep indexing a repository that has
        since been paused, which is the opposite of what pausing means.
        """
        repository_id = context["repository"].repository_id
        context["manager"].transition(repository_id, status)
        job = make_job(repository_id, JobKind.ACQUIRE_REPOSITORY)
        with pytest.raises(ApplicationError, match="withdrawn"):
            context["handlers"].acquire_repository(job)
        assert context["mirrors"].acquired == []

    def test_refusal_is_not_retryable(self, context) -> None:
        """The refusal is a permanent condition, so the runner must not retry it.

        Retrying would burn the attempt budget on a state only an operator can change.
        """
        repository_id = context["repository"].repository_id
        context["manager"].transition(repository_id, RepositoryStatus.PAUSED)
        job = make_job(repository_id, JobKind.ACQUIRE_REPOSITORY)
        with pytest.raises(ApplicationError) as caught:
            context["handlers"].acquire_repository(job)
        assert caught.value.is_retryable is False

    def test_allows_an_active_repository(self, context) -> None:
        """A repository in service is processed normally."""
        repository_id = context["repository"].repository_id
        context["manager"].transition(repository_id, RepositoryStatus.INDEXING)
        job = make_job(repository_id, JobKind.ACQUIRE_REPOSITORY)
        context["handlers"].acquire_repository(job)
        assert context["mirrors"].acquired == ["acme/widgets"]

    def test_raises_for_an_unregistered_repository(self, context) -> None:
        """A job whose repository was purged fails rather than acting on nothing."""
        job = make_job(RepositoryId.generate(), JobKind.ACQUIRE_REPOSITORY)
        with pytest.raises(RepositoryNotFoundError):
            context["handlers"].acquire_repository(job)

    def test_the_repository_is_reloaded_on_every_attempt(self, context) -> None:
        """Configuration is read now, not captured when the job was enqueued.

        If an operator tightened a limit or paused the repository in the interim, the
        attempt must honour that rather than the state at enqueue time.
        """
        repository_id = context["repository"].repository_id
        job = make_job(repository_id, JobKind.ACQUIRE_REPOSITORY)
        context["handlers"].acquire_repository(job)
        context["manager"].transition(repository_id, RepositoryStatus.PAUSED)
        with pytest.raises(ApplicationError, match="withdrawn"):
            context["handlers"].acquire_repository(job)
