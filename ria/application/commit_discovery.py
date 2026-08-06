"""Commit and branch discovery.

Walks a repository's history, records the commits the index policy selects, and
enqueues ingestion work for them.

Cadence is a policy decision, applied here
------------------------------------------
Twin Spec section 6.3 states that indexing every commit on every branch is "neither
affordable nor useful", and gives a cadence table. This is the only place that table
is interpreted: it selects which discovered commits become work, so a change of
policy changes what is enqueued without touching the pipeline that processes it.

Idempotency
-----------
Discovery is the operation most likely to be re-run — on every push, on every poll,
after every restart. It is therefore idempotent at three levels: recording a commit
is an upsert, enqueueing uses a derived idempotency key, and a commit already
queryable is not re-enqueued. A second pass over an unchanged repository performs no
writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from ria.domain.enums import BranchCadence, IngestionStage, JobKind
from ria.domain.errors import RepositoryNotFoundError
from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.branch import Branch
from ria.domain.models.job import Job, JobId, RetryPolicy
from ria.domain.models.progress import ProgressEvent
from ria.domain.models.repository import IndexPolicy, Repository
from ria.observability.logging import get_logger, log_context
from ria.ports.clock import Clock
from ria.ports.git_client import GitClient, RawCommitSummary
from ria.ports.metrics import MetricsSink
from ria.ports.progress import ProgressSink
from ria.ports.unit_of_work import UnitOfWorkFactory

__all__ = ["DiscoveryResult", "CommitDiscovery", "ingest_commit_key"]

_LOGGER = get_logger(__name__)

#: Metric names emitted by this service.
_METRIC_DISCOVERED = "ria_discovery_commits_total"
_METRIC_ENQUEUED = "ria_discovery_enqueued_total"
_METRIC_SECONDS = "ria_discovery_seconds"

#: Default ceiling on a single discovery walk. Bounded because an unbounded walk over
#: a repository with a hundred thousand commits would enqueue more work than any
#: operator intended from a single push event.
DEFAULT_DISCOVERY_LIMIT = 500


def ingest_commit_key(sha: CommitSha) -> str:
    """Build the idempotency key of a commit ingestion job.

    Derived from the commit rather than random, which is what makes enqueueing
    idempotent: two discovery passes over the same commit produce the same key, and
    the queue's unique constraint collapses them into one job.

    Args:
        sha: Commit to ingest.

    Returns:
        The idempotency key.
    """
    return f"{JobKind.INGEST_COMMIT.value}:{sha.value}"


@dataclass(frozen=True)
class DiscoveryResult:
    """Outcome of a discovery pass.

    Attributes:
        branches_recorded: Branches observed and persisted.
        commits_examined: Commits returned by the history walk.
        commits_selected: Commits the cadence policy selected for indexing.
        commits_already_indexed: Selected commits that were already queryable and so
            were not enqueued.
        jobs_enqueued: Ingestion jobs created. Excludes those already queued, so a
            re-run reports zero.
        head_sha: Commit the discovered ref resolved to.
    """

    head_sha: CommitSha
    branches_recorded: int = 0
    commits_examined: int = 0
    commits_selected: int = 0
    commits_already_indexed: int = 0
    jobs_enqueued: int = 0

    @property
    def performed_work(self) -> bool:
        """Whether the pass created any work.

        ``False`` on a re-run over an unchanged repository, which is the property that
        makes discovery safe to trigger on every push.
        """
        return self.jobs_enqueued > 0


class CommitDiscovery:
    """Records commits and branches, and enqueues ingestion work.

    Args:
        git: Read access to the repository mirror.
        unit_of_work_factory: Creates a transaction per operation.
        clock: Source of timestamps.
        metrics: Sink for counts and durations.
        progress: Destination for progress events.
        retry_policy: Policy applied to the ingestion jobs this service enqueues.
    """

    def __init__(
        self,
        git: GitClient,
        unit_of_work_factory: UnitOfWorkFactory,
        clock: Clock,
        metrics: MetricsSink,
        progress: ProgressSink,
        *,
        retry_policy: Optional[RetryPolicy] = None,
    ) -> None:
        self._git = git
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock
        self._metrics = metrics
        self._progress = progress
        self._retry_policy = retry_policy or RetryPolicy()

    def discover(
        self,
        repository: Repository,
        mirror_path: Path,
        *,
        ref: Optional[str] = None,
        limit: int = DEFAULT_DISCOVERY_LIMIT,
        since: Optional[datetime] = None,
        job_id: Optional[str] = None,
    ) -> DiscoveryResult:
        """Record branches and commits, and enqueue ingestion work.

        Args:
            repository: Repository to discover.
            mirror_path: Path of the repository mirror.
            ref: Ref to walk. Defaults to the repository's default branch.
            limit: Maximum commits to examine in this pass.
            since: Only examine commits at or after this instant.
            job_id: Job driving the work, recorded on progress events.

        Returns:
            What the pass observed and enqueued.

        Raises:
            RepositoryNotFoundError: If the repository is not registered.
            RefNotFoundError: If the ref does not resolve.
            GitCommandError: If a git invocation fails.
            StorageError: If a write fails.
        """
        target_ref = ref or repository.default_branch
        with log_context(
            repository=str(repository.moniker),
            repository_id=str(repository.repository_id),
        ):
            with self._metrics.timer(_METRIC_SECONDS, labels={"operation": "discover"}):
                branches = self._observe_branches(repository, mirror_path)
                head = CommitSha(self._git.resolve_ref(mirror_path, target_ref))
                summaries = self._git.list_commits(
                    mirror_path, target_ref, limit=limit, since=since
                )
                self._emit(
                    repository.repository_id,
                    completed=0,
                    total=len(summaries),
                    job_id=job_id,
                    message=f"walking {target_ref}",
                )
                selected = self._select(
                    summaries, repository.index_policy, target_ref, repository
                )
                enqueued, already_indexed = self._persist(
                    repository, branches, selected
                )

            self._metrics.increment(_METRIC_DISCOVERED, value=len(summaries))
            self._metrics.increment(_METRIC_ENQUEUED, value=enqueued)
            self._emit(
                repository.repository_id,
                completed=len(summaries),
                total=len(summaries),
                job_id=job_id,
                message=f"selected {len(selected)}, enqueued {enqueued}",
            )
            _LOGGER.info(
                "commit discovery complete",
                extra={
                    "ref": target_ref,
                    "head": head.short,
                    "examined": len(summaries),
                    "selected": len(selected),
                    "already_indexed": already_indexed,
                    "enqueued": enqueued,
                    "branches": len(branches),
                },
            )
        return DiscoveryResult(
            head_sha=head,
            branches_recorded=len(branches),
            commits_examined=len(summaries),
            commits_selected=len(selected),
            commits_already_indexed=already_indexed,
            jobs_enqueued=enqueued,
        )

    # -- stages -----------------------------------------------------------

    def _observe_branches(
        self, repository: Repository, mirror_path: Path
    ) -> Sequence[Branch]:
        """Read the branch set from the mirror.

        Args:
            repository: Owning repository.
            mirror_path: Path of the mirror.

        Returns:
            The observed branches, excluding those the policy treats as stale.
        """
        now = self._clock.now()
        observed = self._git.list_branches(mirror_path)
        branches = [
            Branch(
                repository_id=repository.repository_id,
                name=raw.name,
                head_sha=CommitSha(raw.head_sha),
                updated_at=now,
                is_default=raw.is_default,
                last_commit_at=raw.last_commit_at,
            )
            for raw in observed
        ]
        # Stale branches are recorded but will not be selected for indexing, so they
        # are kept here: dropping them would make the branch list disagree with the
        # repository, and a consumer asking "what branches exist" would get a
        # filtered answer to an unfiltered question.
        return tuple(branches)

    def _select(
        self,
        summaries: Sequence[RawCommitSummary],
        policy: IndexPolicy,
        ref: str,
        repository: Repository,
    ) -> Sequence[RawCommitSummary]:
        """Apply the snapshot cadence policy to the walked commits.

        Args:
            summaries: Commits returned by the walk, newest first.
            policy: Index policy of the repository.
            ref: Ref that was walked.
            repository: Repository, used to decide whether the ref is the default.

        Returns:
            The commits selected for indexing.
        """
        is_default = ref == repository.default_branch
        cadence = policy.cadence_for(is_default_branch=is_default)

        if cadence is BranchCadence.NEVER:
            return ()
        if cadence is BranchCadence.EVERY_COMMIT:
            return tuple(summaries)
        if cadence is BranchCadence.HEAD_ONLY:
            return tuple(summaries[:1])
        # MERGE_ONLY. The head is always included even when it is not a merge:
        # excluding it would leave the branch tip unindexed, so a query pinned to the
        # branch would resolve to nothing.
        selected: List[RawCommitSummary] = []
        for index, summary in enumerate(summaries):
            if index == 0 or summary.is_merge:
                selected.append(summary)
        return tuple(selected)

    def _persist(
        self,
        repository: Repository,
        branches: Sequence[Branch],
        selected: Sequence[RawCommitSummary],
    ) -> Tuple[int, int]:
        """Write branches and enqueue ingestion work.

        Discovery deliberately writes no commit facts. It has only the sha, parents
        and commit time from the walk, so recording a commit here would mean inventing
        an author, a message and a tree hash — fabricated facts, which PRD principle
        P11 and Twin Spec section 9 both forbid. The ingestion pipeline reads the real
        metadata when it processes the commit, so the queue is the record of
        outstanding work and the commit table holds only observed facts.

        Branches and jobs are written in one transaction, so a crash cannot leave a
        refreshed branch set with no work to process it.

        Args:
            repository: Owning repository.
            branches: Observed branches.
            selected: Commits selected for indexing.

        Returns:
            The number of jobs enqueued and the number of selected commits already
            indexed.

        Raises:
            RepositoryNotFoundError: If the repository is not registered.
        """
        now = self._clock.now()
        enqueued = 0
        already_indexed = 0

        with self._unit_of_work_factory() as unit_of_work:
            if unit_of_work.repositories.get(repository.repository_id) is None:
                raise RepositoryNotFoundError(
                    "repository is not registered",
                    {"repository_id": str(repository.repository_id)},
                )

            unit_of_work.branches.replace_all(repository.repository_id, list(branches))

            for summary in selected:
                sha = CommitSha(summary.sha)
                existing = unit_of_work.commits.get(repository.repository_id, sha)
                if existing is not None and existing.index_state.is_queryable:
                    # Already indexed. Enqueueing would run the whole ingestion again
                    # only to discover it had nothing to do.
                    already_indexed += 1
                    continue

                job = Job(
                    job_id=JobId.generate(),
                    repository_id=repository.repository_id,
                    kind=JobKind.INGEST_COMMIT,
                    idempotency_key=ingest_commit_key(sha),
                    payload={"sha": sha.value},
                    created_at=now,
                    updated_at=now,
                    available_at=now,
                    retry_policy=self._retry_policy,
                )
                stored = unit_of_work.jobs.enqueue(job)
                if stored.job_id == job.job_id:
                    enqueued += 1

            unit_of_work.commit()
        return enqueued, already_indexed

    def _emit(
        self,
        repository_id: RepositoryId,
        *,
        completed: int,
        total: Optional[int],
        job_id: Optional[str],
        message: Optional[str] = None,
    ) -> None:
        """Emit one discovery progress event.

        Args:
            repository_id: Owning repository.
            completed: Commits processed.
            total: Commits to process.
            job_id: Job driving the work.
            message: Optional detail.
        """
        self._progress.emit(
            ProgressEvent(
                repository_id=repository_id,
                stage=IngestionStage.DISCOVER,
                at=self._clock.now(),
                job_id=job_id,
                completed=completed,
                total=total,
                message=message,
            )
        )
