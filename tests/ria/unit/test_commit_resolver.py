"""Tests for the commit resolution use case.

The git client is a fake, so these tests pin the use case's guarantees rather than
git's behaviour: full object names only, symbolic refs marked as such, idempotent
recording, and recorded history that cannot be rewritten.
"""

from __future__ import annotations

from datetime import timezone
from pathlib import Path

import pytest

from ria.application.commit_resolver import CommitResolver
from ria.application.repository_manager import (
    RegisterRepositoryCommand,
    RepositoryManager,
)
from ria.domain.enums import CommitIndexState
from ria.domain.errors import (
    CommitNotFoundError,
    ImmutableFactViolationError,
    RefNotFoundError,
    RepositoryNotFoundError,
)
from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.repository import Repository
from ria.observability.metrics import InMemoryMetricsSink
from ria.ports.git_client import RawBranch
from tests.ria.conftest import utc
from tests.ria.fakes import FakeGitClient, FrozenClock, InMemoryUnitOfWorkFactory

ROOT_SHA = "1" * 40
HEAD_SHA = "2" * 40
MERGE_SHA = "3" * 40
REPO_PATH = Path("/mirrors/acme_widgets")


@pytest.fixture
def git() -> FakeGitClient:
    """A git client scripted with a three-commit history."""
    return FakeGitClient(
        refs={
            "main": HEAD_SHA,
            "HEAD": HEAD_SHA,
            "v1.0.0": ROOT_SHA,
            "2222222": HEAD_SHA,
        },
        commits={
            ROOT_SHA: FakeGitClient.commit_fixture(
                ROOT_SHA, message="initial commit", when=utc(2026, 1, 1, 9)
            ),
            HEAD_SHA: FakeGitClient.commit_fixture(
                HEAD_SHA,
                parents=(ROOT_SHA,),
                message="feat: add handler",
                when=utc(2026, 1, 2, 9),
            ),
            MERGE_SHA: FakeGitClient.commit_fixture(
                MERGE_SHA,
                parents=(HEAD_SHA, ROOT_SHA),
                message="merge branch",
                when=utc(2026, 1, 3, 9),
            ),
        },
        branches=[
            RawBranch(
                name="main",
                head_sha=HEAD_SHA,
                is_default=True,
                last_commit_at=utc(2026, 1, 2, 9),
            ),
            RawBranch(
                name="feature/x",
                head_sha=ROOT_SHA,
                is_default=False,
                last_commit_at=utc(2026, 1, 1, 9),
            ),
        ],
    )


@pytest.fixture
def resolver(
    git: FakeGitClient,
    unit_of_work_factory: InMemoryUnitOfWorkFactory,
    clock: FrozenClock,
    metrics: InMemoryMetricsSink,
) -> CommitResolver:
    """A resolver wired to in-memory collaborators."""
    return CommitResolver(git, unit_of_work_factory, clock, metrics)


@pytest.fixture
def repository(
    unit_of_work_factory: InMemoryUnitOfWorkFactory,
    clock: FrozenClock,
    metrics: InMemoryMetricsSink,
) -> Repository:
    """A registered repository the resolver can attach commits to."""
    manager = RepositoryManager(unit_of_work_factory, clock, metrics)
    return manager.register(
        RegisterRepositoryCommand(origin_url="https://github.com/acme/widgets.git")
    )


class TestResolution:
    """Ref resolution without recording."""

    def test_resolves_a_branch_name(self, resolver: CommitResolver) -> None:
        """A branch resolves to a full object name."""
        reference = resolver.resolve(REPO_PATH, "main")
        assert reference.sha == CommitSha(HEAD_SHA)
        assert reference.ref == "main"

    def test_marks_a_branch_as_symbolic(self, resolver: CommitResolver) -> None:
        """A branch may resolve differently later, so it is marked symbolic.

        A cache or audit needs this distinction: a symbolic result is a snapshot of
        a moving pointer, an object name is permanent.
        """
        assert resolver.resolve(REPO_PATH, "main").is_symbolic is True

    def test_marks_a_tag_as_symbolic(self, resolver: CommitResolver) -> None:
        """A tag is a name too, even though it rarely moves."""
        assert resolver.resolve(REPO_PATH, "v1.0.0").is_symbolic is True

    def test_a_full_object_name_is_not_symbolic(self, resolver: CommitResolver) -> None:
        """An object name resolves to itself and cannot move."""
        reference = resolver.resolve(REPO_PATH, HEAD_SHA)
        assert reference.is_symbolic is False

    def test_an_abbreviated_sha_is_expanded_and_marked_symbolic(
        self, resolver: CommitResolver
    ) -> None:
        """Abbreviations are expanded before entering the domain.

        An abbreviation is ambiguous by construction, so it is treated as symbolic
        and the returned pointer always holds the full name.
        """
        reference = resolver.resolve(REPO_PATH, "2222222")
        assert reference.sha == CommitSha(HEAD_SHA)
        assert reference.is_symbolic is True

    def test_trims_surrounding_whitespace(self, resolver: CommitResolver) -> None:
        """A ref expression is normalised before use."""
        assert resolver.resolve(REPO_PATH, "  main  ").ref == "main"

    def test_normalises_before_consulting_git(
        self, resolver: CommitResolver, git: FakeGitClient
    ) -> None:
        """Git receives the normalised expression, not the caller's raw string.

        Normalising afterwards would send an unusable value downstream while
        reporting symbolic status against a different string.
        """
        resolver.resolve(REPO_PATH, "  main  ")
        assert ("resolve_ref", "main") in git.calls

    def test_raises_for_an_unknown_ref(self, resolver: CommitResolver) -> None:
        """An unresolvable ref raises rather than returning a placeholder."""
        with pytest.raises(RefNotFoundError):
            resolver.resolve(REPO_PATH, "does-not-exist")

    @pytest.mark.parametrize("ref", ["", "   "])
    def test_rejects_an_empty_ref_expression(
        self, resolver: CommitResolver, ref: str
    ) -> None:
        """An empty expression identifies nothing and is a caller error."""
        with pytest.raises(ValueError):
            resolver.resolve(REPO_PATH, ref)

    def test_resolution_writes_nothing(
        self, resolver: CommitResolver, unit_of_work_factory: InMemoryUnitOfWorkFactory
    ) -> None:
        """Resolution is a pure read; no transaction is opened."""
        resolver.resolve(REPO_PATH, "main")
        assert unit_of_work_factory.scopes == []

    def test_counts_symbolic_and_direct_resolutions_separately(
        self, resolver: CommitResolver, metrics: InMemoryMetricsSink
    ) -> None:
        """The mix of symbolic and pinned queries is observable."""
        resolver.resolve(REPO_PATH, "main")
        resolver.resolve(REPO_PATH, HEAD_SHA)
        assert (
            metrics.counter_value("ria_commit_resolved_total", {"symbolic": "true"})
            == 1
        )
        assert (
            metrics.counter_value("ria_commit_resolved_total", {"symbolic": "false"})
            == 1
        )


class TestRecording:
    """Resolution combined with recording a commit's facts."""

    def test_records_a_commit(
        self, resolver: CommitResolver, repository: Repository
    ) -> None:
        """A resolved commit's facts are persisted."""
        outcome = resolver.resolve_and_record(
            repository.repository_id, REPO_PATH, "main"
        )
        assert outcome.was_already_recorded is False
        assert outcome.sha == CommitSha(HEAD_SHA)
        assert outcome.commit.subject == "feat: add handler"
        assert outcome.commit.parents == (CommitSha(ROOT_SHA),)

    def test_a_recorded_commit_enters_as_discovered(
        self, resolver: CommitResolver, repository: Repository
    ) -> None:
        """Nothing is indexed yet, so the commit is not visible to queries.

        Entering at any later state would make the commit queryable before its
        facts exist, which is the half-built-index answer SDD section 5.1 forbids.
        """
        outcome = resolver.resolve_and_record(
            repository.repository_id, REPO_PATH, "main"
        )
        assert outcome.commit.index_state is CommitIndexState.DISCOVERED
        assert outcome.commit.index_state.is_queryable is False

    def test_maps_signatures_and_timestamps(
        self, resolver: CommitResolver, repository: Repository
    ) -> None:
        """Author and committer signatures are recorded as observed."""
        commit = resolver.resolve_and_record(
            repository.repository_id, REPO_PATH, "main"
        ).commit
        assert commit.author.email == "ada@example.com"
        assert commit.committer.name == "Ada Lovelace"
        assert commit.authored_at.tzinfo is not None
        assert commit.authored_at.astimezone(timezone.utc) == utc(2026, 1, 2, 9)

    def test_records_a_merge_commit_with_every_parent(
        self, resolver: CommitResolver, repository: Repository
    ) -> None:
        """Merge parents are preserved in git order, which defines the mainline."""
        commit = resolver.resolve_and_record(
            repository.repository_id, REPO_PATH, MERGE_SHA
        ).commit
        assert commit.is_merge is True
        assert commit.parents == (CommitSha(HEAD_SHA), CommitSha(ROOT_SHA))
        assert commit.first_parent == CommitSha(HEAD_SHA)

    def test_recording_is_idempotent(
        self, resolver: CommitResolver, repository: Repository
    ) -> None:
        """Re-resolving the same ref reports the existing record.

        SDD section 4 requires every task to be idempotent, so a retried job must
        not fail and must not duplicate.
        """
        first = resolver.resolve_and_record(repository.repository_id, REPO_PATH, "main")
        second = resolver.resolve_and_record(
            repository.repository_id, REPO_PATH, "main"
        )
        assert first.was_already_recorded is False
        assert second.was_already_recorded is True
        assert second.commit.sha == first.commit.sha

    def test_idempotent_recording_preserves_processing_state(
        self,
        resolver: CommitResolver,
        repository: Repository,
        unit_of_work_factory: InMemoryUnitOfWorkFactory,
    ) -> None:
        """Re-observing a commit does not reset work already done on it.

        Without this, a routine re-resolution would drag a queryable commit back to
        ``DISCOVERED`` and silently invalidate its index.
        """
        resolver.resolve_and_record(repository.repository_id, REPO_PATH, "main")
        with unit_of_work_factory() as unit_of_work:
            stored = unit_of_work.commits.get(
                repository.repository_id, CommitSha(HEAD_SHA)
            )
            advanced = stored.transition_to(CommitIndexState.PENDING).transition_to(
                CommitIndexState.INDEXING
            )
            unit_of_work.commits.save(advanced)
            unit_of_work.commit()

        again = resolver.resolve_and_record(repository.repository_id, REPO_PATH, "main")
        assert again.was_already_recorded is True
        assert again.commit.index_state is CommitIndexState.INDEXING

    def test_re_observation_of_a_queryable_commit_is_permitted(
        self,
        resolver: CommitResolver,
        repository: Repository,
        unit_of_work_factory: InMemoryUnitOfWorkFactory,
    ) -> None:
        """Identical facts re-observed against a frozen commit are accepted.

        The immutability rule forbids *changing* facts, not confirming them.
        """
        resolver.resolve_and_record(repository.repository_id, REPO_PATH, "main")
        with unit_of_work_factory() as unit_of_work:
            stored = unit_of_work.commits.get(
                repository.repository_id, CommitSha(HEAD_SHA)
            )
            queryable = (
                stored.transition_to(CommitIndexState.PENDING)
                .transition_to(CommitIndexState.INDEXING)
                .transition_to(CommitIndexState.QUERYABLE, now=utc(2026, 1, 4))
            )
            unit_of_work.commits.save(queryable)
            unit_of_work.commit()

        outcome = resolver.resolve_and_record(
            repository.repository_id, REPO_PATH, "main"
        )
        assert outcome.commit.index_state is CommitIndexState.QUERYABLE

    def test_rewriting_a_queryable_commit_is_refused(
        self,
        resolver: CommitResolver,
        repository: Repository,
        unit_of_work_factory: InMemoryUnitOfWorkFactory,
    ) -> None:
        """Changed facts on a frozen commit raise rather than overwriting history.

        This is the enforcement point for the Twin Spec section 3.2 rule that a
        commit is never updated after reaching ``queryable``.
        """
        resolver.resolve_and_record(repository.repository_id, REPO_PATH, "main")
        with unit_of_work_factory() as unit_of_work:
            stored = unit_of_work.commits.get(
                repository.repository_id, CommitSha(HEAD_SHA)
            )
            queryable = (
                stored.transition_to(CommitIndexState.PENDING)
                .transition_to(CommitIndexState.INDEXING)
                .transition_to(CommitIndexState.QUERYABLE, now=utc(2026, 1, 4))
            )
            unit_of_work.commits.save(queryable)
            unit_of_work.commit()

            rewritten = queryable.__class__(
                repository_id=queryable.repository_id,
                sha=queryable.sha,
                parents=queryable.parents,
                author=queryable.author,
                committer=queryable.committer,
                authored_at=queryable.authored_at,
                committed_at=queryable.committed_at,
                message="history rewritten",
                tree_hash=queryable.tree_hash,
                index_state=CommitIndexState.QUERYABLE,
                indexed_at=queryable.indexed_at,
            )
            with pytest.raises(ImmutableFactViolationError):
                unit_of_work.commits.save(rewritten)

    def test_raises_for_an_unregistered_repository(
        self, resolver: CommitResolver
    ) -> None:
        """A commit cannot be attached to a repository that does not exist.

        Recording it would create an orphaned fact whose owning repository is
        unknown, and no query could ever reach it.
        """
        with pytest.raises(RepositoryNotFoundError):
            resolver.resolve_and_record(RepositoryId.generate(), REPO_PATH, "main")

    def test_counts_first_and_repeat_recordings_separately(
        self,
        resolver: CommitResolver,
        repository: Repository,
        metrics: InMemoryMetricsSink,
    ) -> None:
        """New and already-known commits are distinguishable in metrics."""
        resolver.resolve_and_record(repository.repository_id, REPO_PATH, "main")
        resolver.resolve_and_record(repository.repository_id, REPO_PATH, "main")
        assert (
            metrics.counter_value("ria_commit_recorded_total", {"outcome": "recorded"})
            == 1
        )
        assert (
            metrics.counter_value(
                "ria_commit_recorded_total", {"outcome": "already_recorded"}
            )
            == 1
        )


class TestReads:
    """Loading recorded commits."""

    def test_get_returns_a_recorded_commit(
        self, resolver: CommitResolver, repository: Repository
    ) -> None:
        """A recorded commit is retrievable by object name."""
        resolver.resolve_and_record(repository.repository_id, REPO_PATH, "main")
        commit = resolver.get(repository.repository_id, CommitSha(HEAD_SHA))
        assert commit.sha == CommitSha(HEAD_SHA)

    def test_get_raises_for_an_unrecorded_commit(
        self, resolver: CommitResolver, repository: Repository
    ) -> None:
        """An unrecorded commit raises with context."""
        with pytest.raises(CommitNotFoundError):
            resolver.get(repository.repository_id, CommitSha(MERGE_SHA))

    def test_latest_queryable_is_none_before_any_build(
        self, resolver: CommitResolver, repository: Repository
    ) -> None:
        """A discovered commit is deliberately invisible until indexed."""
        resolver.resolve_and_record(repository.repository_id, REPO_PATH, "main")
        assert resolver.latest_queryable(repository.repository_id) is None

    def test_latest_queryable_picks_the_newest_committed(
        self,
        resolver: CommitResolver,
        repository: Repository,
        unit_of_work_factory: InMemoryUnitOfWorkFactory,
    ) -> None:
        """An unpinned query resolves to the newest fully indexed commit."""
        for ref in (ROOT_SHA, HEAD_SHA):
            resolver.resolve_and_record(repository.repository_id, REPO_PATH, ref)
        with unit_of_work_factory() as unit_of_work:
            for sha in (ROOT_SHA, HEAD_SHA):
                stored = unit_of_work.commits.get(
                    repository.repository_id, CommitSha(sha)
                )
                unit_of_work.commits.save(
                    stored.transition_to(CommitIndexState.PENDING)
                    .transition_to(CommitIndexState.INDEXING)
                    .transition_to(CommitIndexState.QUERYABLE, now=utc(2026, 1, 5))
                )
            unit_of_work.commit()

        latest = resolver.latest_queryable(repository.repository_id)
        assert latest is not None
        assert latest.sha == CommitSha(HEAD_SHA)

    def test_pending_work_is_oldest_first(
        self,
        resolver: CommitResolver,
        repository: Repository,
        unit_of_work_factory: InMemoryUnitOfWorkFactory,
    ) -> None:
        """Work proceeds in history order so parse caches are reused.

        A later commit's incremental build reuses the earlier commit's cache, so
        processing newest-first would discard that advantage.
        """
        for ref in (HEAD_SHA, ROOT_SHA):
            resolver.resolve_and_record(repository.repository_id, REPO_PATH, ref)
        with unit_of_work_factory() as unit_of_work:
            for sha in (HEAD_SHA, ROOT_SHA):
                stored = unit_of_work.commits.get(
                    repository.repository_id, CommitSha(sha)
                )
                unit_of_work.commits.save(
                    stored.transition_to(CommitIndexState.PENDING)
                )
            unit_of_work.commit()

        pending = resolver.pending_work(repository.repository_id)
        assert [commit.sha.value for commit in pending] == [ROOT_SHA, HEAD_SHA]


class TestBranchRecording:
    """Observing and recording the branch set."""

    def test_records_every_observed_branch(
        self, resolver: CommitResolver, repository: Repository
    ) -> None:
        """Each observed branch is persisted with its head pointer."""
        assert resolver.record_branches(repository.repository_id, REPO_PATH) == 2

    def test_marks_the_default_branch(
        self,
        resolver: CommitResolver,
        repository: Repository,
        unit_of_work_factory: InMemoryUnitOfWorkFactory,
    ) -> None:
        """The default branch is identifiable without re-consulting git."""
        resolver.record_branches(repository.repository_id, REPO_PATH)
        with unit_of_work_factory() as unit_of_work:
            default = unit_of_work.branches.get_default(repository.repository_id)
        assert default is not None
        assert default.name == "main"

    def test_replacement_removes_a_deleted_branch(
        self,
        resolver: CommitResolver,
        repository: Repository,
        git: FakeGitClient,
        unit_of_work_factory: InMemoryUnitOfWorkFactory,
    ) -> None:
        """Upstream branch deletion is reflected locally.

        Deletion can only be detected by comparing whole sets, which is why the
        operation replaces rather than merges.
        """
        resolver.record_branches(repository.repository_id, REPO_PATH)
        git.branches = [branch for branch in git.branches if branch.is_default]
        resolver.record_branches(repository.repository_id, REPO_PATH)
        with unit_of_work_factory() as unit_of_work:
            names = [
                branch.name
                for branch in unit_of_work.branches.list(repository.repository_id)
            ]
        assert names == ["main"]

    def test_recording_is_idempotent(
        self, resolver: CommitResolver, repository: Repository
    ) -> None:
        """Re-observing an unchanged branch set is a no-op that cannot fail."""
        resolver.record_branches(repository.repository_id, REPO_PATH)
        assert resolver.record_branches(repository.repository_id, REPO_PATH) == 2

    def test_raises_for_an_unregistered_repository(
        self, resolver: CommitResolver
    ) -> None:
        """Branches cannot be attached to a repository that does not exist."""
        with pytest.raises(RepositoryNotFoundError):
            resolver.record_branches(RepositoryId.generate(), REPO_PATH)
