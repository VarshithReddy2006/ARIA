"""Job handlers for the ingestion pipeline.

Binds each :class:`~ria.domain.enums.JobKind` to the use case that performs it.

Why the binding is a module and not the container
-------------------------------------------------
The container's job is to choose adapters; deciding what a job kind *means* is
application logic. Putting the mapping here keeps the composition root free of
behaviour, and lets a test assemble a handler set over fakes without building a
container.

Why every handler loads the repository itself
---------------------------------------------
A job payload carries strings only, because the queue is durable and a payload must
survive a round trip through storage without a type registry. The repository entity is
therefore loaded from the identifier on each attempt rather than captured when the job
was enqueued — which is also the correct behaviour: a job enqueued an hour ago must
act on the repository's configuration as it is now, not as it was then. If an operator
tightened an admission limit or paused the repository in the interim, the attempt must
honour that.
"""

from __future__ import annotations

from typing import Dict, Optional

from ria.application.commit_discovery import CommitDiscovery
from ria.application.ingestion_service import IngestionService
from ria.application.mirror_manager import MirrorManager
from ria.application.repository_manager import RepositoryManager
from ria.domain.enums import JobKind, RepositoryStatus
from ria.domain.errors import ApplicationError
from ria.domain.models.job import Job
from ria.domain.models.repository import Repository
from ria.observability.logging import get_logger
from ria.ports.metrics import MetricsSink

__all__ = [
    "PAYLOAD_REF",
    "PAYLOAD_SHA",
    "PAYLOAD_LIMIT",
    "IngestionHandlers",
    "build_ingestion_handlers",
]

_LOGGER = get_logger(__name__)

#: Payload key naming a ref expression to discover from.
PAYLOAD_REF = "ref"
#: Payload key naming the commit an ingestion job must build.
PAYLOAD_SHA = "sha"
#: Payload key bounding how many commits a discovery pass walks.
PAYLOAD_LIMIT = "limit"

#: Metric emitted once per handled job kind.
_METRIC_HANDLED = "ria_ingestion_jobs_handled_total"

#: Repository states from which queued work must not proceed. A job enqueued before
#: an operator paused or archived a repository would otherwise keep running against a
#: repository that has been withdrawn.
_WITHDRAWN = (RepositoryStatus.PAUSED, RepositoryStatus.ARCHIVED)


class IngestionHandlers:
    """Executes ingestion job kinds against the application services.

    Args:
        repository_manager: Loads repositories and records their lifecycle.
        mirror_manager: Acquires and locates repository mirrors.
        commit_discovery: Records branches and commits and enqueues ingestion work.
        ingestion_service: Ingests one commit.
        metrics: Sink for handled-job counts.
    """

    def __init__(
        self,
        repository_manager: RepositoryManager,
        mirror_manager: MirrorManager,
        commit_discovery: CommitDiscovery,
        ingestion_service: IngestionService,
        metrics: MetricsSink,
    ) -> None:
        self._repositories = repository_manager
        self._mirrors = mirror_manager
        self._discovery = commit_discovery
        self._ingestion = ingestion_service
        self._metrics = metrics

    # -- handlers ---------------------------------------------------------

    def acquire_repository(self, job: Job) -> None:
        """Clone or refresh a repository's mirror.

        Acquisition is its own job kind rather than a step inside ingestion. The two
        have different failure modes — an unreachable origin against a corrupt tree —
        and different retry profiles, so folding them together would make one job's
        backoff schedule serve two unrelated faults.

        Args:
            job: The leased job.

        Raises:
            RepositoryNotFoundError: If the repository is not registered.
            ApplicationError: If the repository has been withdrawn.
            GitCommandError: If the clone or fetch fails.
        """
        repository = self._load(job)
        state = self._mirrors.acquire(repository, refresh=True)
        self._metrics.increment(
            _METRIC_HANDLED,
            labels={
                "kind": JobKind.ACQUIRE_REPOSITORY.value,
                "outcome": "cloned" if state.was_cloned else "fetched",
            },
        )
        _LOGGER.info(
            "mirror acquired",
            extra={
                "repository": repository.slug,
                "cloned": state.was_cloned,
                "fetched": state.was_fetched,
            },
        )

    def discover_commits(self, job: Job) -> None:
        """Record branches and commits, and enqueue ingestion work.

        Args:
            job: The leased job. Payload may carry ``ref`` and ``limit``.

        Raises:
            RepositoryNotFoundError: If the repository is not registered.
            ApplicationError: If the repository has been withdrawn, or the payload
                carries a non-numeric limit.
            MirrorNotFoundError: If no mirror is present.
        """
        repository = self._load(job)
        mirror_path = self._mirrors.require(repository.moniker)
        result = self._discovery.discover(
            repository,
            mirror_path,
            ref=job.payload.get(PAYLOAD_REF),
            job_id=str(job.job_id),
            **self._optional_limit(job),
        )
        self._metrics.increment(
            _METRIC_HANDLED,
            labels={"kind": JobKind.DISCOVER_COMMITS.value, "outcome": "completed"},
        )
        _LOGGER.info(
            "discovery complete",
            extra={"repository": repository.slug, "result": str(result)},
        )

    def ingest_commit(self, job: Job) -> None:
        """Enumerate, hash, store and persist one commit's tree.

        Args:
            job: The leased job. Payload must carry ``sha``.

        Raises:
            RepositoryNotFoundError: If the repository is not registered.
            ApplicationError: If the repository has been withdrawn or the payload
                lacks the commit.
            AdmissionRejectedError: If the tree exceeds a stated limit.
            MirrorNotFoundError: If no mirror is present.
        """
        repository = self._load(job)
        sha = job.require(PAYLOAD_SHA)
        result = self._ingestion.ingest_commit(repository, sha, job_id=str(job.job_id))
        self._metrics.increment(
            _METRIC_HANDLED,
            labels={
                "kind": JobKind.INGEST_COMMIT.value,
                "outcome": "skipped" if result.was_already_indexed else "ingested",
            },
        )

    # -- registry ---------------------------------------------------------

    def as_mapping(self) -> Dict[JobKind, object]:
        """Return the handler for every kind this class implements.

        A kind absent from the returned mapping is dead-lettered by the runner rather
        than left in the queue, so an incomplete registry fails visibly.
        """
        return {
            JobKind.ACQUIRE_REPOSITORY: self.acquire_repository,
            JobKind.DISCOVER_COMMITS: self.discover_commits,
            JobKind.INGEST_COMMIT: self.ingest_commit,
        }

    # -- internals --------------------------------------------------------

    def _load(self, job: Job) -> Repository:
        """Load the job's repository and verify it is still eligible for work.

        Args:
            job: The leased job.

        Returns:
            The repository.

        Raises:
            RepositoryNotFoundError: If the repository is not registered.
            ApplicationError: If the repository has been paused or archived.
        """
        repository = self._repositories.get(job.repository_id)
        if repository.status in _WITHDRAWN:
            raise ApplicationError(
                "repository has been withdrawn from indexing",
                {
                    "repository": repository.slug,
                    "status": repository.status.value,
                    "job_kind": job.kind.value,
                },
            )
        return repository

    @staticmethod
    def _optional_limit(job: Job) -> Dict[str, int]:
        """Extract a discovery limit from the payload, if present.

        Returned as keyword arguments rather than a value so that an absent limit uses
        the service's own default instead of a duplicate of it declared here.

        Args:
            job: The leased job.

        Returns:
            Either an empty mapping or one carrying ``limit``.

        Raises:
            ApplicationError: If the payload carries a limit that is not a positive
                integer. Silently ignoring it would walk a different number of commits
                than the caller asked for.
        """
        raw: Optional[str] = job.payload.get(PAYLOAD_LIMIT)
        if raw is None:
            return {}
        try:
            limit = int(raw)
        except (TypeError, ValueError) as exc:
            raise ApplicationError(
                "discovery limit in job payload is not an integer",
                {"limit": raw, "job_id": str(job.job_id)},
            ) from exc
        if limit < 1:
            raise ApplicationError(
                "discovery limit in job payload must be positive",
                {"limit": raw, "job_id": str(job.job_id)},
            )
        return {"limit": limit}


def build_ingestion_handlers(
    repository_manager: RepositoryManager,
    mirror_manager: MirrorManager,
    commit_discovery: CommitDiscovery,
    ingestion_service: IngestionService,
    metrics: MetricsSink,
) -> Dict[JobKind, object]:
    """Assemble the handler mapping a :class:`~ria.application.job_runner.JobRunner` needs.

    Args:
        repository_manager: Loads repositories and records their lifecycle.
        mirror_manager: Acquires and locates repository mirrors.
        commit_discovery: Records branches and commits.
        ingestion_service: Ingests one commit.
        metrics: Sink for handled-job counts.

    Returns:
        Handler per job kind.
    """
    return IngestionHandlers(
        repository_manager=repository_manager,
        mirror_manager=mirror_manager,
        commit_discovery=commit_discovery,
        ingestion_service=ingestion_service,
        metrics=metrics,
    ).as_mapping()
