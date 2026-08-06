"""Integration tests for the SQLite persistence adapters.

These tests exercise real transactions against a real database file. Three
guarantees are only observable here and not in a unit test:

* rollback by default, so an uncommitted scope leaves no trace;
* fact immutability, enforced by comparing the stored fingerprint on write;
* cascade deletion, which makes the terminal ``archived -> purged`` step a single
  statement.
"""

from __future__ import annotations

import pytest

from ria.container import Container
from ria.domain.enums import (
    CommitIndexState,
    FileClassification,
    LanguageTier,
    ParseStatus,
    RepositoryStatus,
)
from ria.domain.errors import (
    CommitNotFoundError,
    ImmutableFactViolationError,
    RepositoryAlreadyExistsError,
    RepositoryNotFoundError,
    StorageError,
)
from ria.domain.identity import CommitSha, ContentHash, Moniker, RepositoryId
from ria.domain.models.branch import Branch
from ria.domain.models.commit import ChangeStats, Commit, CommitCoverage
from ria.domain.models.file_unit import FileUnit
from ria.domain.models.person import PersonRef
from ria.domain.models.repository import (
    IndexPolicy,
    LanguageProfile,
    Repository,
    SizeMetrics,
)
from tests.ria.conftest import utc

NOW = utc(2026, 1, 1, 12)
LATER = utc(2026, 1, 2, 12)
SHA_A = CommitSha("a" * 40)
SHA_B = CommitSha("b" * 40)


def make_repository(**overrides) -> Repository:
    """Build a repository for persistence tests.

    Args:
        **overrides: Fields to replace.
    """
    defaults = dict(
        repository_id=RepositoryId.generate(),
        moniker=Moniker.for_repository(host="github.com", owner="acme", name="widgets"),
        origin_url="https://github.com/acme/widgets.git",
        default_branch="main",
        tenant_id="tenant-a",
        registered_at=NOW,
        updated_at=NOW,
    )
    defaults.update(overrides)
    return Repository(**defaults)


def make_commit(
    repository_id: RepositoryId, sha: CommitSha = SHA_A, **overrides
) -> Commit:
    """Build a commit for persistence tests.

    Args:
        repository_id: Owning repository.
        sha: Commit object name.
        **overrides: Fields to replace.
    """
    defaults = dict(
        repository_id=repository_id,
        sha=sha,
        parents=(),
        author=PersonRef(name="Ada Lovelace", email="ada@example.com"),
        committer=PersonRef(name="Ada Lovelace", email="ada@example.com"),
        authored_at=NOW,
        committed_at=NOW,
        message="feat: add handler\n\nBody.",
        tree_hash="t" * 40,
    )
    defaults.update(overrides)
    return Commit(**defaults)


def make_unit(
    repository_id: RepositoryId, path: str, sha: CommitSha = SHA_A, **overrides
) -> FileUnit:
    """Build a file unit for persistence tests.

    Args:
        repository_id: Owning repository.
        path: Repository-relative path.
        sha: Commit the unit belongs to.
        **overrides: Fields to replace.
    """
    defaults = dict(
        repository_id=repository_id,
        commit_sha=sha,
        path=path,
        content_hash=ContentHash.of_bytes(path.encode()),
        blob_sha="c" * 40,
        language="python",
        language_tier=LanguageTier.NONE,
        size_bytes=len(path),
        line_count=3,
        classification=FileClassification.SOURCE,
    )
    defaults.update(overrides)
    return FileUnit(**defaults)


def persist(container: Container, repository: Repository) -> Repository:
    """Insert a repository and commit the transaction.

    Args:
        container: Wired container.
        repository: Repository to insert.

    Returns:
        The inserted repository.
    """
    with container.unit_of_work_factory() as unit_of_work:
        unit_of_work.repositories.add(repository)
        unit_of_work.commit()
    return repository


class TestTransactionSemantics:
    """Behaviour of the unit of work."""

    def test_commit_makes_writes_durable(self, container: Container) -> None:
        """Committed writes are visible to a later transaction."""
        repository = persist(container, make_repository())
        with container.unit_of_work_factory() as unit_of_work:
            assert unit_of_work.repositories.get(repository.repository_id) is not None

    def test_rollback_is_the_default(self, container: Container) -> None:
        """Leaving a scope without committing discards the work.

        An exception, an early return and a forgotten commit therefore all abandon
        the work rather than half-applying it.
        """
        repository = make_repository()
        with container.unit_of_work_factory() as unit_of_work:
            unit_of_work.repositories.add(repository)
        with container.unit_of_work_factory() as unit_of_work:
            assert unit_of_work.repositories.get(repository.repository_id) is None

    def test_an_exception_rolls_back(self, container: Container) -> None:
        """A raising block leaves nothing behind."""
        repository = make_repository()
        with pytest.raises(RuntimeError):
            with container.unit_of_work_factory() as unit_of_work:
                unit_of_work.repositories.add(repository)
                raise RuntimeError("boom")
        with container.unit_of_work_factory() as unit_of_work:
            assert unit_of_work.repositories.get(repository.repository_id) is None

    def test_stores_are_unusable_outside_a_scope(self, container: Container) -> None:
        """A leaked store reference cannot write outside a transaction.

        Without this the atomic visibility guarantee of SDD section 5.1 would hold
        only by convention.
        """
        unit_of_work = container.unit_of_work_factory()
        with pytest.raises(StorageError, match="not open"):
            unit_of_work.repositories.get(RepositoryId.generate())

    def test_a_scope_is_single_use(self, container: Container) -> None:
        """Reopening a closed scope raises rather than sharing a transaction."""
        unit_of_work = container.unit_of_work_factory()
        with unit_of_work:
            pass
        with pytest.raises(StorageError, match="already been closed"):
            unit_of_work.__enter__()

    def test_a_multi_store_write_is_atomic(self, container: Container) -> None:
        """Writes across aggregates land together or not at all.

        Making a commit queryable means writing its file units, coverage and index
        state in one transaction, which is why the transaction boundary sits above
        the individual stores.
        """
        repository = persist(container, make_repository())
        commit = make_commit(repository.repository_id)
        with pytest.raises(RuntimeError):
            with container.unit_of_work_factory() as unit_of_work:
                unit_of_work.commits.add(commit)
                unit_of_work.file_units.add_many(
                    [make_unit(repository.repository_id, "src/a.py")]
                )
                raise RuntimeError("boom")
        with container.unit_of_work_factory() as unit_of_work:
            assert unit_of_work.commits.get(repository.repository_id, SHA_A) is None
            assert (
                unit_of_work.file_units.count_by_commit(repository.repository_id, SHA_A)
                == 0
            )

    def test_transactions_are_counted(self, container: Container) -> None:
        """Committed and rolled back transactions are separately observable."""
        persist(container, make_repository())
        with container.unit_of_work_factory():
            pass
        counters = container.metrics.counters()
        rendered = {str(key): value for key, value in counters.items()}
        assert rendered.get("ria_storage_transactions_total{outcome=committed}", 0) >= 1
        assert (
            rendered.get("ria_storage_transactions_total{outcome=rolled_back}", 0) >= 1
        )


class TestRepositoryStore:
    """Persistence of the repository aggregate."""

    def test_round_trips_every_field(self, container: Container) -> None:
        """A repository survives storage without losing structured state.

        Index policy, language profiles and size metrics are stored as JSON, so the
        round trip is the only proof the mapping is lossless.
        """
        repository = make_repository(
            status=RepositoryStatus.ACTIVE,
            index_policy=IndexPolicy(stale_branch_days=45),
            languages=(
                LanguageProfile(
                    language="python",
                    loc=900,
                    percentage=90.0,
                    tier=LanguageTier.NONE,
                    precision=None,
                ),
            ),
            frameworks=("fastapi", "pytest"),
            size_metrics=SizeMetrics(
                files=42, loc=1000, measured_at=NOW, measured_at_sha=SHA_A.value
            ),
            last_indexed_at=NOW,
            last_indexed_sha=SHA_A.value,
        )
        persist(container, repository)
        with container.unit_of_work_factory() as unit_of_work:
            loaded = unit_of_work.repositories.get(repository.repository_id)
        assert loaded == repository

    def test_preserves_unmeasured_as_none(self, container: Container) -> None:
        """An unmeasured value round-trips as ``None``, never as zero.

        Twin Spec section 9 requires the distinction; collapsing it in storage would
        turn "not yet measured" into "measured as none present".
        """
        repository = persist(container, make_repository())
        with container.unit_of_work_factory() as unit_of_work:
            loaded = unit_of_work.repositories.get(repository.repository_id)
        assert loaded.size_metrics.symbols is None
        assert loaded.size_metrics.is_measured is False
        assert loaded.last_indexed_at is None

    def test_preserves_a_degraded_reason(self, container: Container) -> None:
        """Degradation and its cause are stored together."""
        repository = make_repository(
            status=RepositoryStatus.DEGRADED, degraded_reason="clone timed out"
        )
        persist(container, repository)
        with container.unit_of_work_factory() as unit_of_work:
            loaded = unit_of_work.repositories.get(repository.repository_id)
        assert loaded.degraded_reason == "clone timed out"

    def test_rejects_a_duplicate_moniker(self, container: Container) -> None:
        """Logical identity is unique, enforced by the database."""
        persist(container, make_repository())
        with pytest.raises(RepositoryAlreadyExistsError):
            with container.unit_of_work_factory() as unit_of_work:
                unit_of_work.repositories.add(make_repository())

    def test_save_updates_an_existing_record(self, container: Container) -> None:
        """Mutation replaces the stored state."""
        repository = persist(container, make_repository())
        updated = repository.transition_to(RepositoryStatus.INDEXING, now=LATER)
        with container.unit_of_work_factory() as unit_of_work:
            unit_of_work.repositories.save(updated)
            unit_of_work.commit()
        with container.unit_of_work_factory() as unit_of_work:
            loaded = unit_of_work.repositories.get(repository.repository_id)
        assert loaded.status is RepositoryStatus.INDEXING
        assert loaded.updated_at == LATER

    def test_save_raises_for_an_absent_record(self, container: Container) -> None:
        """Updating something unregistered raises rather than inserting."""
        with pytest.raises(RepositoryNotFoundError):
            with container.unit_of_work_factory() as unit_of_work:
                unit_of_work.repositories.save(make_repository())

    def test_lookup_by_moniker(self, container: Container) -> None:
        """A repository is addressable by logical identity."""
        repository = persist(container, make_repository())
        with container.unit_of_work_factory() as unit_of_work:
            loaded = unit_of_work.repositories.get_by_moniker(repository.moniker)
        assert loaded.repository_id == repository.repository_id

    def test_list_is_ordered_by_moniker(self, container: Container) -> None:
        """Ordering is stable, which is a precondition for response caching."""
        for owner in ("zeta", "alpha", "middle"):
            persist(
                container,
                make_repository(
                    moniker=Moniker.for_repository(
                        host="github.com", owner=owner, name="widgets"
                    )
                ),
            )
        with container.unit_of_work_factory() as unit_of_work:
            listed = unit_of_work.repositories.list()
        assert [repository.owner for repository in listed] == [
            "alpha",
            "middle",
            "zeta",
        ]

    def test_list_filters_and_paginates(self, container: Container) -> None:
        """Filtering and windowing happen in the database, not the caller."""
        for index, owner in enumerate(("a", "b", "c")):
            persist(
                container,
                make_repository(
                    moniker=Moniker.for_repository(
                        host="github.com", owner=owner, name="widgets"
                    ),
                    tenant_id="tenant-a" if index < 2 else "tenant-b",
                ),
            )
        with container.unit_of_work_factory() as unit_of_work:
            assert unit_of_work.repositories.count(tenant_id="tenant-a") == 2
            page = unit_of_work.repositories.list(
                tenant_id="tenant-a", limit=1, offset=1
            )
        assert [repository.owner for repository in page] == ["b"]


class TestCommitStore:
    """Persistence of commits and enforcement of fact immutability."""

    def test_round_trips_every_field(self, container: Container) -> None:
        """A commit survives storage including parents and change statistics."""
        repository = persist(container, make_repository())
        commit = make_commit(
            repository.repository_id,
            parents=(SHA_B,),
            change_stats=ChangeStats(files_changed=3, insertions=40, deletions=5),
        )
        with container.unit_of_work_factory() as unit_of_work:
            unit_of_work.commits.add(commit)
            unit_of_work.commit()
        with container.unit_of_work_factory() as unit_of_work:
            loaded = unit_of_work.commits.get(repository.repository_id, SHA_A)
        assert loaded == commit
        assert loaded.parents == (SHA_B,)
        assert loaded.change_stats.churn == 45

    def test_round_trips_coverage(self, container: Container) -> None:
        """The coverage self-report survives storage, including unmeasured fields."""
        repository = persist(container, make_repository())
        coverage = CommitCoverage(
            files_total=100, files_eligible=80, files_parsed=79, symbols_total=None
        )
        commit = make_commit(
            repository.repository_id, index_state=CommitIndexState.INDEXING
        ).transition_to(CommitIndexState.QUERYABLE, now=LATER, coverage=coverage)
        with container.unit_of_work_factory() as unit_of_work:
            unit_of_work.commits.add(commit)
            unit_of_work.commit()
        with container.unit_of_work_factory() as unit_of_work:
            loaded = unit_of_work.commits.get(repository.repository_id, SHA_A)
        assert loaded.coverage == coverage
        assert loaded.coverage.symbols_resolved_pct is None

    def test_requires_a_registered_repository(self, container: Container) -> None:
        """A commit cannot be orphaned from its repository.

        The foreign key means a fact can never exist without an owner no query
        could reach.
        """
        with pytest.raises(StorageError):
            with container.unit_of_work_factory() as unit_of_work:
                unit_of_work.commits.add(make_commit(RepositoryId.generate()))

    def test_add_rejects_a_duplicate(self, container: Container) -> None:
        """The composite primary key prevents a second insert."""
        repository = persist(container, make_repository())
        with container.unit_of_work_factory() as unit_of_work:
            unit_of_work.commits.add(make_commit(repository.repository_id))
            unit_of_work.commit()
        with pytest.raises(StorageError):
            with container.unit_of_work_factory() as unit_of_work:
                unit_of_work.commits.add(make_commit(repository.repository_id))

    def test_upsert_is_idempotent(self, container: Container) -> None:
        """Repeated discovery of the same commit cannot fail."""
        repository = persist(container, make_repository())
        commit = make_commit(repository.repository_id)
        for _ in range(3):
            with container.unit_of_work_factory() as unit_of_work:
                unit_of_work.commits.upsert(commit)
                unit_of_work.commit()
        with container.unit_of_work_factory() as unit_of_work:
            assert unit_of_work.commits.count_by_state(repository.repository_id) == {
                "discovered": 1
            }

    def test_save_raises_for_an_absent_commit(self, container: Container) -> None:
        """Updating an unrecorded commit raises rather than inserting."""
        repository = persist(container, make_repository())
        with pytest.raises(CommitNotFoundError):
            with container.unit_of_work_factory() as unit_of_work:
                unit_of_work.commits.save(make_commit(repository.repository_id))

    def test_state_advances_while_facts_are_mutable(self, container: Container) -> None:
        """Before a commit is queryable, its processing state moves freely."""
        repository = persist(container, make_repository())
        commit = make_commit(repository.repository_id)
        with container.unit_of_work_factory() as unit_of_work:
            unit_of_work.commits.add(commit)
            unit_of_work.commits.save(commit.transition_to(CommitIndexState.PENDING))
            unit_of_work.commit()
        with container.unit_of_work_factory() as unit_of_work:
            loaded = unit_of_work.commits.get(repository.repository_id, SHA_A)
        assert loaded.index_state is CommitIndexState.PENDING

    def test_refuses_to_rewrite_the_facts_of_a_queryable_commit(
        self, container: Container
    ) -> None:
        """The adapter enforces the immutability rule of Twin Spec section 3.2.

        Enforcing this in the adapter rather than only in the entity matters because
        the entity cannot know what was previously stored, and any code path that
        constructs a fresh entity from re-observed git data would bypass an
        in-memory check.
        """
        repository = persist(container, make_repository())
        queryable = make_commit(
            repository.repository_id, index_state=CommitIndexState.INDEXING
        ).transition_to(CommitIndexState.QUERYABLE, now=LATER)
        with container.unit_of_work_factory() as unit_of_work:
            unit_of_work.commits.add(queryable)
            unit_of_work.commit()

        rewritten = make_commit(
            repository.repository_id,
            message="history rewritten",
            index_state=CommitIndexState.QUERYABLE,
            indexed_at=LATER,
        )
        with pytest.raises(ImmutableFactViolationError):
            with container.unit_of_work_factory() as unit_of_work:
                unit_of_work.commits.save(rewritten)

    def test_permits_re_observation_of_identical_facts(
        self, container: Container
    ) -> None:
        """Confirming unchanged facts is permitted; only changing them is not."""
        repository = persist(container, make_repository())
        queryable = make_commit(
            repository.repository_id, index_state=CommitIndexState.INDEXING
        ).transition_to(CommitIndexState.QUERYABLE, now=LATER)
        with container.unit_of_work_factory() as unit_of_work:
            unit_of_work.commits.add(queryable)
            unit_of_work.commits.upsert(queryable)
            unit_of_work.commit()
        with container.unit_of_work_factory() as unit_of_work:
            assert unit_of_work.commits.exists(repository.repository_id, SHA_A)

    def test_orphaning_a_queryable_commit_is_permitted(
        self, container: Container
    ) -> None:
        """A history rewrite marks the commit orphaned and keeps its facts."""
        repository = persist(container, make_repository())
        queryable = make_commit(
            repository.repository_id, index_state=CommitIndexState.INDEXING
        ).transition_to(CommitIndexState.QUERYABLE, now=LATER)
        with container.unit_of_work_factory() as unit_of_work:
            unit_of_work.commits.add(queryable)
            unit_of_work.commits.save(queryable.mark_orphaned())
            unit_of_work.commit()
        with container.unit_of_work_factory() as unit_of_work:
            loaded = unit_of_work.commits.get(repository.repository_id, SHA_A)
        assert loaded.index_state is CommitIndexState.ORPHANED
        assert loaded.message == queryable.message

    def test_work_selection_is_oldest_committed_first(
        self, container: Container
    ) -> None:
        """History order is the processing order, so parse caches are reused."""
        repository = persist(container, make_repository())
        older = make_commit(
            repository.repository_id,
            sha=SHA_B,
            committed_at=utc(2026, 1, 1),
            index_state=CommitIndexState.PENDING,
        )
        newer = make_commit(
            repository.repository_id,
            sha=SHA_A,
            committed_at=utc(2026, 1, 5),
            index_state=CommitIndexState.PENDING,
        )
        with container.unit_of_work_factory() as unit_of_work:
            unit_of_work.commits.add(newer)
            unit_of_work.commits.add(older)
            unit_of_work.commit()
        with container.unit_of_work_factory() as unit_of_work:
            pending = unit_of_work.commits.list_by_state(
                repository.repository_id, CommitIndexState.PENDING
            )
        assert [commit.sha for commit in pending] == [SHA_B, SHA_A]

    def test_latest_queryable_ignores_unfinished_builds(
        self, container: Container
    ) -> None:
        """A commit still being indexed is invisible to an unpinned query.

        This is atomic visibility: only a completed build may be resolved to.
        """
        repository = persist(container, make_repository())
        indexed = make_commit(
            repository.repository_id,
            sha=SHA_B,
            committed_at=utc(2026, 1, 1),
            index_state=CommitIndexState.INDEXING,
        ).transition_to(CommitIndexState.QUERYABLE, now=LATER)
        in_flight = make_commit(
            repository.repository_id,
            sha=SHA_A,
            committed_at=utc(2026, 1, 5),
            index_state=CommitIndexState.INDEXING,
        )
        with container.unit_of_work_factory() as unit_of_work:
            unit_of_work.commits.add(indexed)
            unit_of_work.commits.add(in_flight)
            unit_of_work.commit()
        with container.unit_of_work_factory() as unit_of_work:
            latest = unit_of_work.commits.latest_queryable(repository.repository_id)
        assert latest.sha == SHA_B

    def test_counts_by_state_omit_empty_states(self, container: Container) -> None:
        """The index status report lists only states that have commits."""
        repository = persist(container, make_repository())
        with container.unit_of_work_factory() as unit_of_work:
            unit_of_work.commits.add(make_commit(repository.repository_id, sha=SHA_A))
            unit_of_work.commits.add(
                make_commit(
                    repository.repository_id,
                    sha=SHA_B,
                    index_state=CommitIndexState.PENDING,
                )
            )
            unit_of_work.commit()
        with container.unit_of_work_factory() as unit_of_work:
            counts = unit_of_work.commits.count_by_state(repository.repository_id)
        assert counts == {"discovered": 1, "pending": 1}

    def test_list_by_state_rejects_a_negative_limit(self, container: Container) -> None:
        """A nonsensical limit is rejected rather than passed to SQL."""
        repository = persist(container, make_repository())
        with container.unit_of_work_factory() as unit_of_work:
            with pytest.raises(ValueError):
                unit_of_work.commits.list_by_state(
                    repository.repository_id, CommitIndexState.PENDING, limit=-1
                )


class TestBranchStore:
    """Persistence of branches."""

    def test_round_trips_a_branch(self, container: Container) -> None:
        """A branch survives storage including its merge base cache."""
        repository = persist(container, make_repository())
        branch = Branch(
            repository_id=repository.repository_id,
            name="feature/x",
            head_sha=SHA_A,
            updated_at=NOW,
            is_protected=True,
            last_commit_at=NOW,
        ).with_merge_base("main", SHA_B.value)
        with container.unit_of_work_factory() as unit_of_work:
            unit_of_work.branches.upsert(branch)
            unit_of_work.commit()
        with container.unit_of_work_factory() as unit_of_work:
            loaded = unit_of_work.branches.get(repository.repository_id, "feature/x")
        assert loaded == branch
        assert loaded.merge_base_cache["main"] == SHA_B.value

    def test_upsert_moves_the_pointer(self, container: Container) -> None:
        """A branch is a pointer, so recording it again simply moves it."""
        repository = persist(container, make_repository())
        branch = Branch(
            repository_id=repository.repository_id,
            name="main",
            head_sha=SHA_A,
            updated_at=NOW,
            is_default=True,
        )
        with container.unit_of_work_factory() as unit_of_work:
            unit_of_work.branches.upsert(branch)
            unit_of_work.branches.upsert(branch.moved_to(SHA_B, now=LATER))
            unit_of_work.commit()
        with container.unit_of_work_factory() as unit_of_work:
            loaded = unit_of_work.branches.get(repository.repository_id, "main")
        assert loaded.head_sha == SHA_B
        assert loaded.merge_base_cache == {}

    def test_identifies_the_default_branch(self, container: Container) -> None:
        """The default branch is retrievable without consulting git."""
        repository = persist(container, make_repository())
        with container.unit_of_work_factory() as unit_of_work:
            unit_of_work.branches.upsert(
                Branch(
                    repository_id=repository.repository_id,
                    name="main",
                    head_sha=SHA_A,
                    updated_at=NOW,
                    is_default=True,
                )
            )
            unit_of_work.branches.upsert(
                Branch(
                    repository_id=repository.repository_id,
                    name="feature/x",
                    head_sha=SHA_B,
                    updated_at=NOW,
                )
            )
            unit_of_work.commit()
        with container.unit_of_work_factory() as unit_of_work:
            default = unit_of_work.branches.get_default(repository.repository_id)
            listed = unit_of_work.branches.list(repository.repository_id)
        assert default.name == "main"
        assert [branch.name for branch in listed] == ["feature/x", "main"]

    def test_replace_all_removes_deleted_branches(self, container: Container) -> None:
        """Upstream deletion is reflected because whole sets are compared."""
        repository = persist(container, make_repository())
        first = Branch(
            repository_id=repository.repository_id,
            name="main",
            head_sha=SHA_A,
            updated_at=NOW,
            is_default=True,
        )
        second = Branch(
            repository_id=repository.repository_id,
            name="feature/x",
            head_sha=SHA_B,
            updated_at=NOW,
        )
        with container.unit_of_work_factory() as unit_of_work:
            unit_of_work.branches.replace_all(repository.repository_id, [first, second])
            unit_of_work.commit()
        with container.unit_of_work_factory() as unit_of_work:
            unit_of_work.branches.replace_all(repository.repository_id, [first])
            unit_of_work.commit()
        with container.unit_of_work_factory() as unit_of_work:
            listed = unit_of_work.branches.list(repository.repository_id)
        assert [branch.name for branch in listed] == ["main"]

    def test_replace_all_is_atomic(self, container: Container) -> None:
        """No consumer observes an empty branch list mid-replacement."""
        repository = persist(container, make_repository())
        branch = Branch(
            repository_id=repository.repository_id,
            name="main",
            head_sha=SHA_A,
            updated_at=NOW,
            is_default=True,
        )
        with container.unit_of_work_factory() as unit_of_work:
            unit_of_work.branches.replace_all(repository.repository_id, [branch])
            unit_of_work.commit()
        with pytest.raises(RuntimeError):
            with container.unit_of_work_factory() as unit_of_work:
                unit_of_work.branches.replace_all(repository.repository_id, [])
                raise RuntimeError("boom")
        with container.unit_of_work_factory() as unit_of_work:
            assert len(unit_of_work.branches.list(repository.repository_id)) == 1

    def test_delete_removes_one_branch(self, container: Container) -> None:
        """A single branch record can be removed."""
        repository = persist(container, make_repository())
        with container.unit_of_work_factory() as unit_of_work:
            unit_of_work.branches.upsert(
                Branch(
                    repository_id=repository.repository_id,
                    name="feature/x",
                    head_sha=SHA_A,
                    updated_at=NOW,
                )
            )
            unit_of_work.commit()
        with container.unit_of_work_factory() as unit_of_work:
            assert unit_of_work.branches.delete(repository.repository_id, "feature/x")
            assert not unit_of_work.branches.delete(repository.repository_id, "absent")
            unit_of_work.commit()


class TestFileUnitStore:
    """Persistence of file units."""

    def test_bulk_insert_and_ordered_read(self, container: Container) -> None:
        """Units are written in bulk and read back ordered by path."""
        repository = persist(container, make_repository())
        units = [
            make_unit(repository.repository_id, "src/z.py"),
            make_unit(repository.repository_id, "README.md"),
            make_unit(repository.repository_id, "src/a.py"),
        ]
        with container.unit_of_work_factory() as unit_of_work:
            assert unit_of_work.file_units.add_many(units) == 3
            unit_of_work.commit()
        with container.unit_of_work_factory() as unit_of_work:
            loaded = unit_of_work.file_units.list_by_commit(
                repository.repository_id, SHA_A
            )
        assert [unit.path for unit in loaded] == ["README.md", "src/a.py", "src/z.py"]

    def test_round_trips_every_field(self, container: Container) -> None:
        """A unit survives storage including its parse outcome and reason."""
        repository = persist(container, make_repository())
        unit = make_unit(
            repository.repository_id,
            "src/big.py",
            parse_status=ParseStatus.SKIPPED,
            parse_status_reason="exceeds max_file_bytes",
            line_count=None,
        )
        with container.unit_of_work_factory() as unit_of_work:
            unit_of_work.file_units.add_many([unit])
            unit_of_work.commit()
        with container.unit_of_work_factory() as unit_of_work:
            loaded = unit_of_work.file_units.get(
                repository.repository_id, SHA_A, "src/big.py"
            )
        assert loaded == unit
        assert loaded.parse_status_reason == "exceeds max_file_bytes"
        assert loaded.line_count is None

    def test_rejects_a_batch_spanning_commits(self, container: Container) -> None:
        """A mixed batch is refused rather than silently written.

        Writing it would attribute one commit's files to another, and every fact
        derived from the tree would then describe a tree that never existed.
        """
        repository = persist(container, make_repository())
        units = [
            make_unit(repository.repository_id, "a.py", sha=SHA_A),
            make_unit(repository.repository_id, "b.py", sha=SHA_B),
        ]
        with container.unit_of_work_factory() as unit_of_work:
            with pytest.raises(ValueError):
                unit_of_work.file_units.add_many(units)

    def test_empty_batch_is_a_no_op(self, container: Container) -> None:
        """An empty batch writes nothing and does not raise."""
        with container.unit_of_work_factory() as unit_of_work:
            assert unit_of_work.file_units.add_many([]) == 0

    def test_content_hash_map_avoids_loading_entities(
        self, container: Container
    ) -> None:
        """Change detection reads primitives, not entities.

        Loading a hundred thousand full entities to compare two hashes each would
        dominate the incremental build budget.
        """
        repository = persist(container, make_repository())
        units = [
            make_unit(repository.repository_id, "src/a.py"),
            make_unit(repository.repository_id, "src/b.py"),
        ]
        with container.unit_of_work_factory() as unit_of_work:
            unit_of_work.file_units.add_many(units)
            unit_of_work.commit()
        with container.unit_of_work_factory() as unit_of_work:
            hashes = unit_of_work.file_units.content_hashes_by_commit(
                repository.repository_id, SHA_A
            )
        assert set(hashes) == {"src/a.py", "src/b.py"}
        assert hashes["src/a.py"] == str(ContentHash.of_bytes(b"src/a.py"))

    def test_counts_and_deletes_by_commit(self, container: Container) -> None:
        """Units are countable and removable per commit."""
        repository = persist(container, make_repository())
        with container.unit_of_work_factory() as unit_of_work:
            unit_of_work.file_units.add_many(
                [make_unit(repository.repository_id, "src/a.py")]
            )
            unit_of_work.commit()
        with container.unit_of_work_factory() as unit_of_work:
            assert (
                unit_of_work.file_units.count_by_commit(repository.repository_id, SHA_A)
                == 1
            )
            assert (
                unit_of_work.file_units.delete_by_commit(
                    repository.repository_id, SHA_A
                )
                == 1
            )
            unit_of_work.commit()
        with container.unit_of_work_factory() as unit_of_work:
            assert (
                unit_of_work.file_units.count_by_commit(repository.repository_id, SHA_A)
                == 0
            )

    def test_paginates_a_large_tree(self, container: Container) -> None:
        """Reads are windowed, since a tree may hold hundreds of thousands of units."""
        repository = persist(container, make_repository())
        units = [
            make_unit(repository.repository_id, f"src/file{index:03d}.py")
            for index in range(10)
        ]
        with container.unit_of_work_factory() as unit_of_work:
            unit_of_work.file_units.add_many(units)
            unit_of_work.commit()
        with container.unit_of_work_factory() as unit_of_work:
            page = unit_of_work.file_units.list_by_commit(
                repository.repository_id, SHA_A, limit=3, offset=2
            )
        assert [unit.path for unit in page] == [
            "src/file002.py",
            "src/file003.py",
            "src/file004.py",
        ]


class TestCascadeDeletion:
    """The terminal purge step."""

    def test_purging_a_repository_removes_every_owned_fact(
        self, container: Container
    ) -> None:
        """Cascade deletion makes the purge a single statement.

        Every repository-owned table declares ``ON DELETE CASCADE``, so nothing is
        left behind to become an unreachable orphan.
        """
        repository = persist(container, make_repository())
        with container.unit_of_work_factory() as unit_of_work:
            unit_of_work.commits.add(make_commit(repository.repository_id))
            unit_of_work.branches.upsert(
                Branch(
                    repository_id=repository.repository_id,
                    name="main",
                    head_sha=SHA_A,
                    updated_at=NOW,
                    is_default=True,
                )
            )
            unit_of_work.file_units.add_many(
                [make_unit(repository.repository_id, "src/a.py")]
            )
            unit_of_work.commit()

        with container.unit_of_work_factory() as unit_of_work:
            assert unit_of_work.repositories.delete(repository.repository_id) is True
            unit_of_work.commit()

        with container.unit_of_work_factory() as unit_of_work:
            assert unit_of_work.repositories.get(repository.repository_id) is None
            assert unit_of_work.commits.count_by_state(repository.repository_id) == {}
            assert unit_of_work.branches.list(repository.repository_id) == ()
            assert (
                unit_of_work.file_units.count_by_commit(repository.repository_id, SHA_A)
                == 0
            )

    def test_deleting_an_absent_repository_reports_false(
        self, container: Container
    ) -> None:
        """Deleting nothing is not an error, which keeps retention jobs idempotent."""
        with container.unit_of_work_factory() as unit_of_work:
            assert unit_of_work.repositories.delete(RepositoryId.generate()) is False
