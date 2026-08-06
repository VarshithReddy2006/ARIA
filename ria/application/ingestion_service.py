"""Ingestion orchestrator.

Composes the Milestone 2 pipeline of SDD section 5.1 into one use case: acquire,
resolve, enumerate, hash, store, detect changes, persist, finalise.

Why this is a service and not a request handler
----------------------------------------------
SDD section 3 (L1 defect 1) records that the prior architecture put this orchestration
inside a 330-line generator in an HTTP route, and that the result was "untestable,
unreusable, uninterruptible, unqueueable". Every one of those follows from the
placement rather than from the logic, so the logic lives here and the delivery layer
calls it.

Atomic visibility
-----------------
The persistence step writes the file units, the coverage report and the commit's
transition to ``QUERYABLE`` inside a single transaction. SDD section 5.1 step 9
requires that a commit be invisible until fully indexed and visible immediately
afterwards, because a half-built index "produces answers that are wrong in ways
indistinguishable from right". The transaction boundary is what makes that true
rather than aspirational.

Idempotency
-----------
Re-ingesting a commit is safe and cheap. File units for the commit are deleted before
being rewritten, so a partial previous attempt leaves no residue; content already in
the blob store is neither re-read nor re-written; and a commit that is already
queryable short-circuits before any git access. A retried job therefore converges on
the same state rather than compounding.

What this milestone does not claim
----------------------------------
Coverage is reported with ``files_parsed=0``. No parser exists until Milestone 3, so
any other value would be a fabricated statement about what the index understands,
which PRD principle P11 and Twin Spec section 9 forbid.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Mapping, Optional, Tuple

if TYPE_CHECKING:
    from ria.application.parser_service import ParserService
    from ria.ports.semantic import SemanticResolutionPort
    from ria.ports.graph import GraphBuilderPort

from ria.application.commit_resolver import CommitResolver
from ria.application.file_enumerator import FileEnumerator
from ria.application.mirror_manager import MirrorManager
from ria.domain.diff import compute_change_set
from ria.domain.enums import CommitIndexState, IngestionStage, RepositoryStatus
from ria.domain.errors import RepositoryNotFoundError
from ria.domain.identity import RepositoryId
from ria.domain.models.change_set import ChangeSet
from ria.domain.models.commit import Commit, CommitCoverage, LanguageCoverage
from ria.domain.models.manifest import CommitManifest
from ria.domain.models.progress import ProgressEvent
from ria.domain.models.repository import LanguageProfile, Repository, SizeMetrics
from ria.observability.logging import get_logger, log_context
from ria.ports.clock import Clock
from ria.ports.metrics import MetricsSink
from ria.ports.progress import ProgressSink
from ria.ports.unit_of_work import UnitOfWorkFactory

__all__ = ["IngestionResult", "IngestionService"]

_LOGGER = get_logger(__name__)

#: Metric names emitted by this use case.
_METRIC_INGESTED = "ria_ingestion_commits_total"
_METRIC_STAGE_SECONDS = "ria_ingestion_stage_seconds"
_METRIC_FILES = "ria_ingestion_files_total"
_METRIC_BLOBS = "ria_ingestion_blobs_total"
_METRIC_REUSE_RATIO = "ria_ingestion_blob_reuse_ratio"


@dataclass(frozen=True)
class IngestionResult:
    """Outcome of ingesting one commit.

    Attributes:
        repository_id: Repository ingested.
        commit: The commit in its final state. Queryable on success.
        manifest: The commit's complete file tree.
        change_set: Difference from the first parent, or a full change set when the
            commit has no indexed parent.
        coverage: What the index understands about the commit.
        blobs_stored: Blobs written by this run.
        blobs_reused: Blobs already present, so neither read nor written.
        was_already_indexed: Whether the commit was queryable before this call, in
            which case no git access or storage occurred.
    """

    repository_id: RepositoryId
    commit: Commit
    manifest: CommitManifest
    change_set: ChangeSet
    coverage: CommitCoverage
    blobs_stored: int
    blobs_reused: int
    was_already_indexed: bool = False

    @property
    def file_count(self) -> int:
        """Number of files in the ingested commit."""
        return self.manifest.file_count

    @property
    def reuse_ratio(self) -> float:
        """Fraction of distinct blobs that were already stored, in ``[0, 1]``."""
        considered = self.blobs_stored + self.blobs_reused
        return 1.0 if considered == 0 else self.blobs_reused / considered


class IngestionService:
    """Ingests one commit into the facts store.

    Args:
        mirror_manager: Locates and refreshes repository mirrors.
        commit_resolver: Resolves refs and records commit facts.
        file_enumerator: Builds a manifest from a git tree.
        unit_of_work_factory: Creates a transaction per operation.
        clock: Source of timestamps.
        metrics: Sink for counts and durations.
        progress: Destination for progress events.
    """

    def __init__(
        self,
        mirror_manager: MirrorManager,
        commit_resolver: CommitResolver,
        file_enumerator: FileEnumerator,
        unit_of_work_factory: UnitOfWorkFactory,
        clock: Clock,
        metrics: MetricsSink,
        progress: ProgressSink,
        parser_service: Optional[ParserService] = None,
        semantic_service: Optional[SemanticResolutionPort] = None,
        graph_service: Optional[GraphBuilderPort] = None,
        twin_service: Optional[Any] = None,
    ) -> None:
        self._mirrors = mirror_manager
        self._resolver = commit_resolver
        self._enumerator = file_enumerator
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock
        self._metrics = metrics
        self._progress = progress
        self._parser_service = parser_service
        self._semantic_service = semantic_service
        self._graph_service = graph_service
        self._twin_service = twin_service

    # -- entry point ------------------------------------------------------

    def ingest_commit(
        self,
        repository: Repository,
        ref: str,
        *,
        job_id: Optional[str] = None,
        force: bool = False,
    ) -> IngestionResult:
        """Ingest one commit and make it queryable.

        Args:
            repository: Registered repository to ingest from. Passed as an entity
                rather than an identifier because the caller has already loaded it and
                the admission limits and index policy are read from it.
            ref: Ref expression identifying the commit. A full object name when the
                caller is a queued job, a branch name when a human triggered it.
            job_id: Job driving the work, recorded on progress events.
            force: Re-ingest a commit that is already queryable. Its facts are
                immutable, so only derived data is rewritten.

        Returns:
            The ingestion outcome.

        Raises:
            RepositoryNotFoundError: If the repository is not registered.
            MirrorNotFoundError: If no mirror is present. Acquisition is a separate
                job kind, so ingestion never clones implicitly — an implicit clone
                inside an indexing job would make one job do two unrelated units of
                work with two different failure modes.
            AdmissionRejectedError: If the tree exceeds a stated limit.
            RefNotFoundError: If the ref does not resolve.
            StorageError: If persistence fails.
        """
        repository_id = repository.repository_id
        with log_context(repository=repository.slug, job_id=job_id):
            mirror_path = self._mirrors.require(repository.moniker)

            resolved = self._stage(
                IngestionStage.RESOLVE,
                repository_id,
                job_id,
                lambda: self._resolver.resolve_and_record(
                    repository_id, mirror_path, ref
                ),
            )
            commit = resolved.commit

            if commit.index_state.is_queryable and not force:
                self._metrics.increment(
                    _METRIC_INGESTED, labels={"outcome": "already_indexed"}
                )
                _LOGGER.info(
                    "commit already indexed; skipping ingestion",
                    extra={"commit": commit.sha.short},
                )
                return self._describe_existing(repository_id, commit)

            self._mark_repository_indexing(repository)
            commit = self._begin(commit)
            try:
                result = self._run(
                    repository=repository,
                    mirror_path=mirror_path,
                    commit=commit,
                    job_id=job_id,
                )
            except Exception as exc:
                self._mark_failed(commit, exc)
                self._metrics.increment(_METRIC_INGESTED, labels={"outcome": "failed"})
                raise
            self._metrics.increment(_METRIC_INGESTED, labels={"outcome": "ingested"})
            return result

    # -- pipeline ---------------------------------------------------------

    def _run(
        self,
        *,
        repository: Repository,
        mirror_path: Path,
        commit: Commit,
        job_id: Optional[str],
    ) -> IngestionResult:
        """Execute the pipeline for a commit whose build has begun.

        Args:
            repository: Repository being ingested.
            mirror_path: Path of the repository mirror.
            commit: Commit in the ``INDEXING`` state.
            job_id: Job driving the work.

        Returns:
            The ingestion outcome.
        """
        repository_id = repository.repository_id

        enumeration = self._stage(
            IngestionStage.ENUMERATE,
            repository_id,
            job_id,
            lambda: self._enumerator.enumerate_commit(
                repository_id=repository_id,
                mirror_path=mirror_path,
                sha=commit.sha,
                limits=repository.index_policy.admission,
                job_id=job_id,
            ),
        )

        # The enumerator reads a tree and therefore cannot know the commit's
        # ancestry. Parents come from the recorded commit, so the manifest is a
        # complete description of one commit rather than of one tree.
        manifest = replace(enumeration.manifest, parent_shas=tuple(commit.parents))

        change_set = self._stage(
            IngestionStage.DETECT_CHANGES,
            repository_id,
            job_id,
            lambda: self._detect_changes(repository_id, commit, manifest),
        )

        if self._parser_service is not None:
            updated_units, coverage, parse_results, summary = self._stage(
                IngestionStage.PARSE,
                repository_id,
                job_id,
                lambda: self._parser_service.parse_commit(manifest.tree, change_set),
            )
            manifest = replace(manifest, tree=updated_units)

            if self._semantic_service is not None:
                resolutions = self._stage(
                    IngestionStage.RESOLVE_SEMANTICS,
                    repository_id,
                    job_id,
                    lambda: [
                        self._semantic_service.resolve_unit(
                            unit, parse_results[unit.path]
                        )
                        for unit in manifest.tree
                        if unit.path in parse_results
                    ],
                )
                if self._graph_service is not None:
                    self._stage(
                        IngestionStage.PERSIST,
                        repository_id,
                        job_id,
                        lambda: self._graph_service.build_graph(
                            repository_id, commit.sha, manifest.tree, resolutions
                        ),
                    )
        else:
            coverage = self._build_coverage(manifest)

        self._stage(
            IngestionStage.PERSIST,
            repository_id,
            job_id,
            lambda: self._persist(commit, manifest, coverage),
        )

        finalised = self._stage(
            IngestionStage.FINALISE,
            repository_id,
            job_id,
            lambda: self._finalise(repository, commit, manifest),
        )

        self._record_metrics(manifest, enumeration)
        self._emit(
            repository_id,
            IngestionStage.FINALISE,
            job_id,
            commit_sha=commit.sha.value,
            completed=manifest.file_count,
            total=manifest.file_count,
            message=str(change_set),
        )
        _LOGGER.info(
            "commit ingested",
            extra={
                "commit": commit.sha.short,
                "files": manifest.file_count,
                "blobs_stored": enumeration.blobs_stored,
                "blobs_reused": enumeration.blobs_reused,
                "changes": dict(change_set.counts()),
            },
        )
        return IngestionResult(
            repository_id=repository_id,
            commit=finalised,
            manifest=manifest,
            change_set=change_set,
            coverage=coverage,
            blobs_stored=enumeration.blobs_stored,
            blobs_reused=enumeration.blobs_reused,
        )

    def _detect_changes(
        self, repository_id: RepositoryId, commit: Commit, manifest: CommitManifest
    ) -> ChangeSet:
        """Diff the commit's tree against its first indexed parent.

        The first parent defines the mainline, so it is the base a change set is
        computed against. A merge's second parent is deliberately ignored: the
        incremental work required is what changed relative to the branch being built
        on, and diffing against both parents would double-count every file the merge
        brought in.

        A parent that is not itself indexed yields a full change set rather than an
        error: the index is allowed to have gaps, and reporting every path as added is
        the honest description of what must be built.

        Args:
            repository_id: Owning repository.
            commit: Commit being ingested.
            manifest: The commit's tree.

        Returns:
            The change set.
        """
        current = {
            path: str(value) for path, value in manifest.content_hashes().items()
        }
        parent = commit.first_parent
        if parent is None:
            return ChangeSet(head_sha=commit.sha.value, added=frozenset(current))

        with self._unit_of_work_factory() as unit_of_work:
            parent_commit = unit_of_work.commits.get(repository_id, parent)
            previous: Optional[Mapping[str, str]] = None
            if parent_commit is not None and parent_commit.index_state.is_queryable:
                previous = unit_of_work.file_units.content_hashes_by_commit(
                    repository_id, parent
                )

        if previous is None:
            return ChangeSet(head_sha=commit.sha.value, added=frozenset(current))
        return compute_change_set(
            head_sha=commit.sha.value,
            current=current,
            previous=previous,
            base_sha=parent.value,
        )

    def _persist(
        self, commit: Commit, manifest: CommitManifest, coverage: CommitCoverage
    ) -> None:
        """Write the tree and make the commit queryable, atomically.

        The delete is what makes a retry safe: a previous attempt that died between
        writing units and committing leaves rows behind, and inserting over them would
        fail on the primary key. Deleting first means the write converges rather than
        conflicting.

        Args:
            commit: Commit being made queryable.
            manifest: Units to write.
            coverage: Coverage to record.

        Raises:
            StorageError: If the write fails.
        """
        now = self._clock.now()
        with self._unit_of_work_factory() as unit_of_work:
            unit_of_work.file_units.delete_by_commit(commit.repository_id, commit.sha)
            unit_of_work.file_units.add_many(list(manifest.tree))
            unit_of_work.commits.save(
                commit.transition_to(
                    CommitIndexState.QUERYABLE, now=now, coverage=coverage
                )
            )
            unit_of_work.commit()

    def _finalise(
        self, repository: Repository, commit: Commit, manifest: CommitManifest
    ) -> Commit:
        """Record measured repository metadata and mark the build successful.

        Args:
            repository: Repository being ingested.
            commit: Commit that was ingested.
            manifest: The commit's tree.

        Returns:
            The commit in its final queryable state.

        Raises:
            RepositoryNotFoundError: If the repository disappeared mid-build.
        """
        now = self._clock.now()
        languages = self._language_profiles(manifest)
        size = SizeMetrics(
            files=manifest.file_count,
            loc=sum(manifest.language_line_counts().values()),
            measured_at=now,
            measured_at_sha=commit.sha.value,
        )

        with self._unit_of_work_factory() as unit_of_work:
            current = unit_of_work.repositories.get(repository.repository_id)
            if current is None:
                raise RepositoryNotFoundError(
                    "repository is not registered",
                    {"repository_id": str(repository.repository_id)},
                )
            updated = current.with_metadata(
                now=now, languages=languages, size_metrics=size
            )
            # A repository that an operator paused or archived mid-build must not be
            # dragged back to active by the build completing.
            if updated.status in (RepositoryStatus.INDEXING, RepositoryStatus.DEGRADED):
                updated = updated.with_successful_index(sha=commit.sha.value, now=now)
            unit_of_work.repositories.save(updated)
            final = unit_of_work.commits.get(repository.repository_id, commit.sha)
            unit_of_work.commit()
        return final if final is not None else commit

    # -- commit state -----------------------------------------------------

    def _mark_repository_indexing(self, repository: Repository) -> None:
        """Move the repository into the ``INDEXING`` state before a build begins.

        The repository lifecycle of Twin Spec section 3.2 is
        ``registered -> first_index -> active``, and ``ACTIVE`` is not reachable
        directly from ``REGISTERED``. Without this step a first successful ingestion
        would complete with the repository still marked ``REGISTERED`` and
        ``last_indexed_sha`` unset, so a status query would report a repository that
        had never been indexed while its commits were queryable.

        Paused and archived repositories are left alone: an operator has withdrawn
        them, and a build already in flight must not drag them back into service.

        Args:
            repository: Repository whose build is starting.
        """
        now = self._clock.now()
        with self._unit_of_work_factory() as unit_of_work:
            current = unit_of_work.repositories.get(repository.repository_id)
            if current is None:
                raise RepositoryNotFoundError(
                    "repository is not registered",
                    {"repository_id": str(repository.repository_id)},
                )
            if current.status in (
                RepositoryStatus.REGISTERED,
                RepositoryStatus.ACTIVE,
                RepositoryStatus.DEGRADED,
            ):
                unit_of_work.repositories.save(
                    current.transition_to(RepositoryStatus.INDEXING, now=now)
                )
            unit_of_work.commit()

    def _begin(self, commit: Commit) -> Commit:
        """Move a commit into the ``INDEXING`` state.

        Advancing through ``PENDING`` rather than jumping is deliberate: the states
        are what a status query reports, and a commit that went straight to
        ``INDEXING`` would never have been observably queued.

        Args:
            commit: Commit to begin building.

        Returns:
            The commit in the ``INDEXING`` state.
        """
        target = commit
        with self._unit_of_work_factory() as unit_of_work:
            if target.index_state is CommitIndexState.DISCOVERED:
                target = target.transition_to(CommitIndexState.PENDING)
                unit_of_work.commits.save(target)
            if target.index_state in (
                CommitIndexState.PENDING,
                CommitIndexState.FAILED,
            ):
                if target.index_state is CommitIndexState.FAILED:
                    target = target.transition_to(CommitIndexState.PENDING)
                    unit_of_work.commits.save(target)
                target = target.transition_to(CommitIndexState.INDEXING)
                unit_of_work.commits.save(target)
            unit_of_work.commit()
        return target

    def _mark_failed(self, commit: Commit, error: BaseException) -> None:
        """Record that a build failed, so the state is honest after the exception.

        Failure to record the failure is swallowed and logged rather than raised: the
        original exception is the one the caller needs, and replacing it with a
        storage error would hide the cause.

        Args:
            commit: Commit whose build failed.
            error: The failure.
        """
        reason = f"{type(error).__name__}: {error}"
        try:
            with self._unit_of_work_factory() as unit_of_work:
                current = unit_of_work.commits.get(commit.repository_id, commit.sha)
                if current is not None and not current.index_state.facts_are_frozen:
                    unit_of_work.commits.save(
                        current.transition_to(
                            CommitIndexState.FAILED, failure_reason=reason
                        )
                    )
                unit_of_work.commit()
        except Exception as nested:  # pragma: no cover - defensive
            _LOGGER.error(
                "could not record ingestion failure",
                extra={"commit": commit.sha.short, "reason": str(nested)},
            )
        _LOGGER.error(
            "ingestion failed", extra={"commit": commit.sha.short, "reason": reason}
        )

    # -- derived reports --------------------------------------------------

    def _build_coverage(self, manifest: CommitManifest) -> CommitCoverage:
        """Build the commit's coverage self-report.

        ``files_parsed`` is zero because no parser exists until Milestone 3. Reporting
        anything else would claim understanding the index does not have, which Twin
        Spec section 9 forbids and which an autonomous consumer would act on.

        Args:
            manifest: The commit's tree.

        Returns:
            The coverage report.
        """
        eligible = manifest.parse_candidates()
        per_language: Dict[str, int] = {}
        for unit in eligible:
            per_language[unit.language] = per_language.get(unit.language, 0) + 1
        return CommitCoverage(
            files_total=manifest.file_count,
            files_eligible=len(eligible),
            files_parsed=0,
            by_language=tuple(
                LanguageCoverage(language=language, files_total=count, files_parsed=0)
                for language, count in sorted(per_language.items())
            ),
        )

    def _language_profiles(
        self, manifest: CommitManifest
    ) -> Tuple[LanguageProfile, ...]:
        """Measure language presence from the manifest.

        Precision is left unset on every profile. PRD principle P8 forbids publishing
        a precision figure that has not been measured, and none has been.

        Args:
            manifest: The commit's tree.

        Returns:
            One profile per language present, ordered by canonical name.
        """
        counts = manifest.language_line_counts()
        total = sum(counts.values())
        tiers = {unit.language: unit.language_tier for unit in manifest.tree}
        return tuple(
            LanguageProfile(
                language=language,
                loc=lines,
                percentage=(100.0 * lines / total) if total else 0.0,
                tier=tiers.get(language) or next(iter(tiers.values())),
            )
            for language, lines in sorted(counts.items())
        )

    def _describe_existing(
        self, repository_id: RepositoryId, commit: Commit
    ) -> IngestionResult:
        """Build a result for a commit that was already queryable.

        Reads the stored tree rather than re-enumerating it, so a redundant call costs
        one query instead of a full ingestion.

        Args:
            repository_id: Owning repository.
            commit: The already-indexed commit.

        Returns:
            The outcome, marked as already indexed.
        """
        with self._unit_of_work_factory() as unit_of_work:
            units = unit_of_work.file_units.list_by_commit(
                repository_id, commit.sha, limit=1_000_000
            )
        manifest = CommitManifest(
            repository_id=repository_id,
            commit_sha=commit.sha,
            parent_shas=tuple(commit.parents),
            tree=tuple(units),
            created_at=self._clock.now(),
        )
        coverage = commit.coverage or self._build_coverage(manifest)
        return IngestionResult(
            repository_id=repository_id,
            commit=commit,
            manifest=manifest,
            change_set=ChangeSet(head_sha=commit.sha.value),
            coverage=coverage,
            blobs_stored=0,
            blobs_reused=len(manifest.distinct_content_hashes()),
            was_already_indexed=True,
        )

    # -- instrumentation --------------------------------------------------

    def _stage(self, stage, repository_id, job_id, action):
        """Run one pipeline stage, timing it and reporting its start.

        Args:
            stage: Stage being executed.
            repository_id: Owning repository.
            job_id: Job driving the work.
            action: Zero-argument callable performing the stage.

        Returns:
            Whatever the action returns.
        """
        self._emit(repository_id, stage, job_id, completed=0, total=None)
        with self._metrics.timer(_METRIC_STAGE_SECONDS, labels={"stage": stage.value}):
            return action()

    def _record_metrics(self, manifest: CommitManifest, enumeration) -> None:
        """Record the run's file and blob counters.

        Args:
            manifest: The ingested tree.
            enumeration: The enumeration outcome.
        """
        self._metrics.increment(
            _METRIC_FILES, value=manifest.file_count, labels={"outcome": "enumerated"}
        )
        self._metrics.increment(
            _METRIC_BLOBS, value=enumeration.blobs_stored, labels={"outcome": "stored"}
        )
        self._metrics.increment(
            _METRIC_BLOBS, value=enumeration.blobs_reused, labels={"outcome": "reused"}
        )
        self._metrics.observe(_METRIC_REUSE_RATIO, enumeration.reuse_ratio)

    def _emit(
        self,
        repository_id: RepositoryId,
        stage: IngestionStage,
        job_id: Optional[str],
        *,
        completed: int = 0,
        total: Optional[int] = None,
        commit_sha: Optional[str] = None,
        message: Optional[str] = None,
    ) -> None:
        """Emit one progress event.

        Args:
            repository_id: Owning repository.
            stage: Stage the observation concerns.
            job_id: Job driving the work.
            completed: Units of work finished.
            total: Units of work in the stage, or ``None`` when not yet known.
            commit_sha: Commit being processed.
            message: Human-readable detail.
        """
        self._progress.emit(
            ProgressEvent(
                repository_id=repository_id,
                stage=stage,
                at=self._clock.now(),
                job_id=job_id,
                commit_sha=commit_sha,
                completed=completed,
                total=total,
                message=message,
            )
        )
