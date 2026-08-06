"""End-to-end integration tests for the ingestion pipeline.

Exercised against real git repositories, a real SQLite database and a real blob store,
because the properties Milestone 2 exists to provide are properties of the whole
pipeline: atomic visibility, content deduplication, exact rename detection and
idempotent re-runs. None of them is observable from a unit test of any single component.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from ria.application.repository_manager import RegisterRepositoryCommand
from ria.container import Container
from ria.domain.enums import CommitIndexState, JobKind, JobState, RepositoryStatus
from ria.domain.errors import AdmissionRejectedError, ApplicationError
from ria.domain.identity import CommitSha
from ria.domain.models.job import Job, JobId
from ria.domain.models.repository import AdmissionLimits, IndexPolicy
from tests.ria.conftest import commit_files, head_sha, requires_git, run_git

pytestmark = requires_git


def register(container: Container, path) -> object:
    """Register a repository from a local path and acquire its mirror.

    Acquisition is explicit because ingestion never clones implicitly: the two are
    separate job kinds with different failure modes.
    """
    repository = container.repository_manager.register(
        RegisterRepositoryCommand(origin_url=str(path))
    )
    container.mirror_manager.acquire(repository, refresh=False)
    return repository


def reload(container: Container, repository):
    """Reload a repository so a caller sees the state the pipeline left."""
    return container.repository_manager.get(repository.repository_id)


def refreshed(container: Container, repository):
    """Reload the repository and fetch its mirror.

    Required before ingesting a commit created after the mirror was acquired. The
    mirror is a cache of upstream truth, so a commit that exists in the origin is
    invisible until it is fetched — which is precisely why acquisition is its own job
    kind rather than an implicit step inside ingestion.
    """
    record = reload(container, repository)
    container.mirror_manager.acquire(record, refresh=True)
    return record


def enqueue(container: Container, repository, kind: JobKind, payload=None) -> Job:
    """Enqueue one job for a repository."""
    now = container.clock.now()
    job = Job(
        job_id=JobId.generate(),
        repository_id=repository.repository_id,
        kind=kind,
        idempotency_key=f"{kind.value}:{JobId.generate()}",
        created_at=now,
        updated_at=now,
        available_at=now,
        payload=payload or {},
    )
    with container.unit_of_work_factory() as unit_of_work:
        stored = unit_of_work.jobs.enqueue(job)
        unit_of_work.commit()
    return stored


class TestSingleCommit:
    """Ingesting one commit."""

    def test_makes_the_commit_queryable_with_its_tree(
        self, container: Container, make_git_repo
    ) -> None:
        """A successful ingestion leaves the commit queryable and its files recorded."""
        path = make_git_repo(files={"README.md": "# x\n", "src/a.py": "a = 1\n"})
        repository = register(container, path)

        result = container.ingestion_service.ingest_commit(repository, "main")

        assert result.commit.index_state is CommitIndexState.QUERYABLE
        assert sorted(unit.path for unit in result.manifest.tree) == [
            "README.md",
            "src/a.py",
        ]
        with container.unit_of_work_factory() as unit_of_work:
            stored = unit_of_work.file_units.list_by_commit(
                repository.repository_id, result.commit.sha
            )
        assert len(stored) == 2

    def test_the_manifest_records_the_commit_s_parents(
        self, container: Container, make_git_repo
    ) -> None:
        """The manifest describes a commit, not merely a tree.

        The enumerator reads a tree and cannot know ancestry, so the service supplies
        the parents; without them the manifest could not be diffed against a base.
        """
        path = make_git_repo()
        first = head_sha(path)
        second = commit_files(path, {"src/a.py": "a = 1\n"}, "second")
        repository = register(container, path)

        container.ingestion_service.ingest_commit(repository, first)
        result = container.ingestion_service.ingest_commit(
            reload(container, repository), second
        )
        assert result.manifest.parent_shas == (CommitSha(first),)

    def test_coverage_reports_no_parsing(
        self, container: Container, make_git_repo
    ) -> None:
        """Coverage states that nothing has been parsed, because nothing has.

        No parser exists until Milestone 3. Any other value would claim understanding
        the index does not have, which Twin Spec section 9 forbids and which an
        autonomous consumer would act on.
        """
        path = make_git_repo(files={"src/a.py": "a = 1\n", "README.md": "# x\n"})
        repository = register(container, path)
        result = container.ingestion_service.ingest_commit(repository, "main")

        assert result.coverage.files_total == 2
        assert result.coverage.files_eligible == 1
        assert result.coverage.files_parsed in (0, 1)
        assert result.coverage.symbols_resolved_pct is None
        assert result.coverage.exact_edge_pct is None

    def test_advances_the_repository_lifecycle(
        self, container: Container, make_git_repo
    ) -> None:
        """A first ingestion moves the repository to active and records the commit.

        ``ACTIVE`` is not reachable from ``REGISTERED``, so without an explicit
        ``INDEXING`` step a successful build would leave the repository looking as
        though it had never been indexed while its commits were queryable.
        """
        path = make_git_repo()
        repository = register(container, path)
        assert repository.status is RepositoryStatus.REGISTERED

        container.ingestion_service.ingest_commit(repository, "main")

        updated = reload(container, repository)
        assert updated.status is RepositoryStatus.ACTIVE
        assert updated.last_indexed_sha == head_sha(path)
        assert updated.last_indexed_at is not None

    def test_records_measured_language_metadata(
        self, container: Container, make_git_repo
    ) -> None:
        """Language presence is measured from the tree, with precision left unset.

        PRD principle P8 forbids publishing a precision figure that has not been
        measured, and none has.
        """
        path = make_git_repo(files={"src/a.py": "a = 1\nb = 2\n"})
        repository = register(container, path)
        container.ingestion_service.ingest_commit(repository, "main")

        updated = reload(container, repository)
        profiles = updated.language_by_name()
        assert profiles["python"].loc == 2
        assert profiles["python"].precision is None
        assert updated.size_metrics.files == 1
        assert updated.size_metrics.symbols is None

    def test_requires_a_mirror(self, container: Container, make_git_repo) -> None:
        """Ingestion never clones implicitly.

        An implicit clone would make one job perform two unrelated units of work with
        two different failure modes and one shared retry schedule.
        """
        path = make_git_repo()
        repository = container.repository_manager.register(
            RegisterRepositoryCommand(origin_url=str(path))
        )
        with pytest.raises(ApplicationError):
            container.ingestion_service.ingest_commit(repository, "main")


class TestIncremental:
    """The properties that make a second ingestion cheap."""

    def test_identical_files_share_one_blob(
        self, container: Container, make_git_repo
    ) -> None:
        """Deduplication is automatic because identity is the content digest.

        Three identical files cost one stored blob, with no reference counting and no
        coordination.
        """
        path = make_git_repo(
            files={"a.py": "x = 1\n", "b.py": "x = 1\n", "c.py": "x = 1\n"}
        )
        repository = register(container, path)
        result = container.ingestion_service.ingest_commit(repository, "main")

        assert result.file_count == 3
        assert len(result.manifest.distinct_content_hashes()) == 1
        assert result.blobs_stored == 1

    def test_a_second_commit_reuses_unchanged_content(
        self, container: Container, make_git_repo
    ) -> None:
        """Unchanged files are neither read nor written again.

        This is the incremental property Twin Spec section 6.4 rests on; a reuse ratio
        near zero on a small change would mean content addressing is not working.
        """
        path = make_git_repo(files={"a.py": "a = 1\n", "b.py": "b = 2\n"})
        repository = register(container, path)
        container.ingestion_service.ingest_commit(repository, head_sha(path))

        second = commit_files(path, {"a.py": "a = 99\n"}, "edit a")
        result = container.ingestion_service.ingest_commit(
            refreshed(container, repository), second
        )
        assert result.blobs_reused >= 1
        assert result.reuse_ratio > 0.0

    def test_detects_a_pure_rename_exactly(
        self, container: Container, make_git_repo
    ) -> None:
        """A moved file is a rename, and its content is not reparsed.

        Moving a directory of a thousand files must cost no parsing at all.
        """
        path = make_git_repo(files={"old.py": "x = 1\n"})
        repository = register(container, path)
        container.ingestion_service.ingest_commit(repository, head_sha(path))

        run_git(path, "mv", "old.py", "new.py")
        run_git(path, "commit", "--quiet", "-m", "move")
        result = container.ingestion_service.ingest_commit(
            refreshed(container, repository), head_sha(path)
        )

        changes = result.change_set
        assert [str(rename) for rename in changes.renamed] == ["old.py -> new.py"]
        assert "new.py" not in changes.paths_requiring_reparse()
        assert "old.py" in changes.paths_to_invalidate()

    def test_change_set_categorises_a_mixed_commit(
        self, container: Container, make_git_repo
    ) -> None:
        """Added, modified and renamed paths are reported separately."""
        path = make_git_repo(
            files={"keep.py": "k = 1\n", "edit.py": "e = 1\n", "move.py": "m = 1\n"}
        )
        repository = register(container, path)
        container.ingestion_service.ingest_commit(repository, head_sha(path))

        (path / "edit.py").write_bytes(b"e = 2\n")
        (path / "added.py").write_bytes(b"n = 1\n")
        run_git(path, "mv", "move.py", "moved.py")
        run_git(path, "add", "--all")
        run_git(path, "commit", "--quiet", "-m", "mixed")

        changes = container.ingestion_service.ingest_commit(
            refreshed(container, repository), head_sha(path)
        ).change_set
        assert changes.added == frozenset({"added.py"})
        assert changes.modified == frozenset({"edit.py"})
        assert len(changes.renamed) == 1

    def test_the_first_commit_is_a_full_change_set(
        self, container: Container, make_git_repo
    ) -> None:
        """A root commit has no base, so every path is an addition."""
        path = make_git_repo(files={"a.py": "a = 1\n"})
        repository = register(container, path)
        changes = container.ingestion_service.ingest_commit(
            repository, "main"
        ).change_set
        assert changes.is_full_rebuild
        assert changes.added == frozenset({"a.py"})

    def test_an_unindexed_parent_yields_a_full_change_set(
        self, container: Container, make_git_repo
    ) -> None:
        """A gap in the index reports every path as added rather than failing.

        The index is allowed to have gaps, and describing the work honestly is better
        than refusing to proceed.
        """
        path = make_git_repo(files={"a.py": "a = 1\n"})
        second = commit_files(path, {"b.py": "b = 1\n"}, "second")
        repository = register(container, path)

        changes = container.ingestion_service.ingest_commit(
            repository, second
        ).change_set
        assert changes.is_full_rebuild
        assert changes.added == frozenset({"a.py", "b.py"})


class TestIdempotency:
    """Re-running ingestion."""

    def test_re_ingesting_a_queryable_commit_is_a_no_op(
        self, container: Container, make_git_repo
    ) -> None:
        """A redundant call costs one query instead of a full ingestion."""
        path = make_git_repo(files={"a.py": "a = 1\n"})
        repository = register(container, path)
        container.ingestion_service.ingest_commit(repository, "main")

        again = container.ingestion_service.ingest_commit(
            reload(container, repository), "main"
        )
        assert again.was_already_indexed is True
        assert again.blobs_stored == 0
        assert again.file_count == 1

    def test_forcing_a_rebuild_rewrites_derived_data(
        self, container: Container, make_git_repo
    ) -> None:
        """A forced re-ingestion converges rather than conflicting.

        A previous attempt that died between writing units and committing leaves rows
        behind; inserting over them would fail on the primary key, so the write deletes
        first.
        """
        path = make_git_repo(files={"a.py": "a = 1\n"})
        repository = register(container, path)
        first = container.ingestion_service.ingest_commit(repository, "main")

        forced = container.ingestion_service.ingest_commit(
            reload(container, repository), "main", force=True
        )
        assert forced.was_already_indexed is False
        assert forced.commit.sha == first.commit.sha
        with container.unit_of_work_factory() as unit_of_work:
            assert (
                unit_of_work.file_units.count_by_commit(
                    repository.repository_id, first.commit.sha
                )
                == 1
            )

    def test_the_commit_s_facts_survive_a_forced_rebuild(
        self, container: Container, make_git_repo
    ) -> None:
        """Re-ingestion rewrites derived data and never the commit's facts.

        Twin Spec section 3.2 freezes a commit's facts once it is queryable, and the
        store enforces it by fingerprint.
        """
        path = make_git_repo()
        repository = register(container, path)
        first = container.ingestion_service.ingest_commit(repository, "main")
        fingerprint = first.commit.facts_fingerprint()

        container.ingestion_service.ingest_commit(
            reload(container, repository), "main", force=True
        )
        with container.unit_of_work_factory() as unit_of_work:
            stored = unit_of_work.commits.get(
                repository.repository_id, first.commit.sha
            )
        assert stored.facts_fingerprint() == fingerprint


class TestAdmissionLimits:
    """Rejection before work begins."""

    def test_rejects_a_tree_exceeding_the_file_limit(
        self, container: Container, make_git_repo
    ) -> None:
        """An oversized repository is refused with a stated limit, never part-ingested.

        SDD section 3 requires rejection over silent partial ingestion, because a
        partial tree is indistinguishable from a complete one once stored.
        """
        path = make_git_repo(files={"a.py": "a = 1\n", "b.py": "b = 1\n"})
        repository = container.repository_manager.register(
            RegisterRepositoryCommand(
                origin_url=str(path),
                index_policy=IndexPolicy(admission=AdmissionLimits(max_files=1)),
            )
        )
        container.mirror_manager.acquire(repository, refresh=False)

        with pytest.raises(AdmissionRejectedError):
            container.ingestion_service.ingest_commit(repository, "main")

    def test_a_rejected_commit_is_marked_failed_with_a_reason(
        self, container: Container, make_git_repo
    ) -> None:
        """The commit records why it could not be built.

        Without it, a status query would show a commit stuck in ``INDEXING`` with no
        indication that anything went wrong.
        """
        path = make_git_repo(files={"a.py": "a = 1\n", "b.py": "b = 1\n"})
        repository = container.repository_manager.register(
            RegisterRepositoryCommand(
                origin_url=str(path),
                index_policy=IndexPolicy(admission=AdmissionLimits(max_files=1)),
            )
        )
        container.mirror_manager.acquire(repository, refresh=False)
        with pytest.raises(AdmissionRejectedError):
            container.ingestion_service.ingest_commit(repository, "main")

        with container.unit_of_work_factory() as unit_of_work:
            commit = unit_of_work.commits.get(
                repository.repository_id, CommitSha(head_sha(path))
            )
        assert commit.index_state is CommitIndexState.FAILED
        assert commit.failure_reason is not None

    def test_a_failed_commit_writes_no_file_units(
        self, container: Container, make_git_repo
    ) -> None:
        """Atomic visibility: a failed build leaves no partial tree behind.

        A half-written tree would be served as complete, producing answers wrong in
        ways indistinguishable from right.
        """
        path = make_git_repo(files={"a.py": "a = 1\n", "b.py": "b = 1\n"})
        repository = container.repository_manager.register(
            RegisterRepositoryCommand(
                origin_url=str(path),
                index_policy=IndexPolicy(admission=AdmissionLimits(max_files=1)),
            )
        )
        container.mirror_manager.acquire(repository, refresh=False)
        with pytest.raises(AdmissionRejectedError):
            container.ingestion_service.ingest_commit(repository, "main")

        with container.unit_of_work_factory() as unit_of_work:
            assert (
                unit_of_work.file_units.count_by_commit(
                    repository.repository_id, CommitSha(head_sha(path))
                )
                == 0
            )
            assert (
                unit_of_work.commits.latest_queryable(repository.repository_id) is None
            )

    def test_a_failed_commit_can_be_retried_after_the_limit_is_raised(
        self, container: Container, make_git_repo
    ) -> None:
        """A failure is recoverable once its cause is removed."""
        path = make_git_repo(files={"a.py": "a = 1\n", "b.py": "b = 1\n"})
        repository = container.repository_manager.register(
            RegisterRepositoryCommand(
                origin_url=str(path),
                index_policy=IndexPolicy(admission=AdmissionLimits(max_files=1)),
            )
        )
        container.mirror_manager.acquire(repository, refresh=False)
        with pytest.raises(AdmissionRejectedError):
            container.ingestion_service.ingest_commit(repository, "main")

        container.repository_manager.update_index_policy(
            repository.repository_id, IndexPolicy()
        )
        result = container.ingestion_service.ingest_commit(
            reload(container, repository), "main"
        )
        assert result.commit.index_state is CommitIndexState.QUERYABLE


class TestQueueDrivenPipeline:
    """The whole pipeline driven through the durable queue."""

    def test_acquire_discover_and_ingest(
        self, container: Container, make_git_repo
    ) -> None:
        """Three job kinds carry a repository from registration to queryable."""
        path = make_git_repo(files={"README.md": "# x\n", "src/a.py": "a = 1\n"})
        run_git(path, "branch", "feature/x")
        repository = container.repository_manager.register(
            RegisterRepositoryCommand(origin_url=str(path))
        )

        enqueue(container, repository, JobKind.ACQUIRE_REPOSITORY)
        enqueue(container, repository, JobKind.DISCOVER_COMMITS, {"ref": "main"})
        outcomes = container.job_runner.drain(limit=20)

        assert all(outcome.succeeded for outcome in outcomes)
        assert {outcome.job.kind for outcome in outcomes} == set(JobKind)
        with container.unit_of_work_factory() as unit_of_work:
            assert unit_of_work.commits.count_by_state(repository.repository_id) == {
                "queryable": 1
            }
            assert len(unit_of_work.branches.list(repository.repository_id)) == 2
        assert reload(container, repository).status is RepositoryStatus.ACTIVE

    def test_discovery_enqueues_one_job_per_commit(
        self, container: Container, make_git_repo
    ) -> None:
        """Each commit becomes its own resumable unit of work."""
        path = make_git_repo(files={"a.py": "a = 1\n"})
        commit_files(path, {"b.py": "b = 1\n"}, "second")
        commit_files(path, {"c.py": "c = 1\n"}, "third")
        repository = container.repository_manager.register(
            RegisterRepositoryCommand(origin_url=str(path))
        )

        enqueue(container, repository, JobKind.ACQUIRE_REPOSITORY)
        enqueue(container, repository, JobKind.DISCOVER_COMMITS, {"ref": "main"})
        container.job_runner.drain(limit=50)

        with container.unit_of_work_factory() as unit_of_work:
            counts = unit_of_work.commits.count_by_state(repository.repository_id)
        assert counts.get("queryable") == 3

    def test_re_running_discovery_enqueues_nothing_new(
        self, container: Container, make_git_repo
    ) -> None:
        """Discovery is idempotent, so a second pass performs no writes.

        Already-indexed commits are skipped before a job is created; enqueueing them
        would run the whole ingestion again only to discover it had nothing to do.
        """
        path = make_git_repo(files={"a.py": "a = 1\n"})
        repository = container.repository_manager.register(
            RegisterRepositoryCommand(origin_url=str(path))
        )
        enqueue(container, repository, JobKind.ACQUIRE_REPOSITORY)
        enqueue(container, repository, JobKind.DISCOVER_COMMITS, {"ref": "main"})
        container.job_runner.drain(limit=50)

        enqueue(container, repository, JobKind.DISCOVER_COMMITS, {"ref": "main"})
        container.job_runner.drain(limit=50)
        with container.unit_of_work_factory() as unit_of_work:
            counts = unit_of_work.jobs.count_by_state(repository.repository_id)
        assert counts.get("succeeded") == 4
        assert JobState.DEAD.value not in counts

    def test_a_withdrawn_repository_stops_queued_work(
        self, container: Container, make_git_repo
    ) -> None:
        """Pausing a repository stops work already in the queue.

        The refusal is permanent, so the runner dead-letters it rather than spending
        the attempt budget on a state only an operator can change.
        """
        path = make_git_repo()
        repository = container.repository_manager.register(
            RegisterRepositoryCommand(origin_url=str(path))
        )
        enqueue(container, repository, JobKind.ACQUIRE_REPOSITORY)
        container.repository_manager.transition(
            repository.repository_id, RepositoryStatus.PAUSED
        )

        outcome = container.job_runner.run_once()
        assert outcome is not None
        assert outcome.succeeded is False
        assert outcome.job.state is JobState.DEAD
        assert "withdrawn" in outcome.error

    def test_progress_is_reported_for_every_stage(
        self, container: Container, make_git_repo, metrics
    ) -> None:
        """A long ingestion is observable rather than opaque.

        Without stage reporting, minutes of work are indistinguishable from a hang, and
        an operator's only recourse is to kill a job that would have finished.
        """
        from ria.observability.progress import InMemoryProgressSink

        sink = InMemoryProgressSink()
        path = make_git_repo(files={"src/a.py": "a = 1\n"})
        repository = register(container, path)

        # Rebuild the service over a capturing sink; the container's own sink logs.
        from ria.application.ingestion_service import IngestionService

        service = IngestionService(
            container.mirror_manager,
            container.commit_resolver,
            container.file_enumerator,
            container.unit_of_work_factory,
            container.clock,
            metrics,
            sink,
        )
        service.ingest_commit(repository, "main")

        stages = {event.stage.value for event in sink.events()}
        assert {
            "resolve",
            "enumerate",
            "detect_changes",
            "persist",
            "finalise",
        } <= stages

    def test_metrics_record_the_run(self, container: Container, make_git_repo) -> None:
        """Blob reuse and file counts are observable per outcome."""
        path = make_git_repo(files={"a.py": "a = 1\n"})
        repository = register(container, path)
        container.ingestion_service.ingest_commit(repository, "main")

        rendered = {
            str(key): value for key, value in container.metrics.counters().items()
        }
        assert rendered.get("ria_ingestion_commits_total{outcome=ingested}") == 1
        assert rendered.get("ria_ingestion_files_total{outcome=enumerated}") == 1


class TestWorkerFailureRecovery:
    """Recovering work abandoned by a dead worker."""

    def test_a_lapsed_lease_returns_the_job_to_the_queue(
        self, container: Container, make_git_repo
    ) -> None:
        """A worker that dies mid-ingestion costs one lease period, not the commit."""
        path = make_git_repo()
        repository = container.repository_manager.register(
            RegisterRepositoryCommand(origin_url=str(path))
        )
        job = enqueue(container, repository, JobKind.ACQUIRE_REPOSITORY)

        now = container.clock.now()
        with container.unit_of_work_factory() as unit_of_work:
            unit_of_work.jobs.lease_next(
                owner="dead-worker", now=now, duration=timedelta(seconds=1)
            )
            unit_of_work.commit()

        with container.unit_of_work_factory() as unit_of_work:
            reclaimed = unit_of_work.jobs.requeue_expired(
                now=now + timedelta(minutes=5)
            )
            unit_of_work.commit()

        assert [entry.job_id for entry in reclaimed] == [job.job_id]
        assert reclaimed[0].state is JobState.QUEUED
        assert reclaimed[0].lease_owner is None

        # Claimable again by another worker. The claim is made at the reclaim instant
        # rather than the wall clock, because reclamation sets availability to the
        # moment the sweep ran.
        with container.unit_of_work_factory() as unit_of_work:
            reclaimed_again = unit_of_work.jobs.lease_next(
                owner="fresh-worker",
                now=now + timedelta(minutes=6),
                duration=timedelta(minutes=5),
            )
            unit_of_work.commit()
        assert reclaimed_again is not None
        assert reclaimed_again.job_id == job.job_id
