"""Tests for the Repository Manager use cases.

Every collaborator is a fake, so these tests exercise use-case logic rather than
storage behaviour. The fake unit of work models rollback, which is what lets a test
assert that a rejected registration left no trace.
"""

from __future__ import annotations

import pytest

from ria.application.repository_manager import (
    RegisterRepositoryCommand,
    RepositoryManager,
    parse_origin_url,
)
from ria.domain.enums import BranchCadence, RepositoryStatus
from ria.domain.errors import (
    ApplicationError,
    IllegalStateTransitionError,
    RepositoryAlreadyExistsError,
    RepositoryNotFoundError,
)
from ria.domain.identity import Moniker, RepositoryId
from ria.domain.models.repository import IndexPolicy, LanguageProfile, SizeMetrics
from ria.domain.enums import LanguageTier
from ria.observability.metrics import InMemoryMetricsSink
from tests.ria.fakes import FrozenClock, InMemoryUnitOfWorkFactory

ORIGIN = "https://github.com/acme/widgets.git"


@pytest.fixture
def manager(
    unit_of_work_factory: InMemoryUnitOfWorkFactory,
    clock: FrozenClock,
    metrics: InMemoryMetricsSink,
) -> RepositoryManager:
    """A manager wired to in-memory collaborators."""
    return RepositoryManager(
        unit_of_work_factory, clock, metrics, default_tenant_id="default"
    )


class TestOriginUrlParsing:
    """Derivation of a moniker and a credential-free origin from a remote."""

    @pytest.mark.parametrize(
        "origin,moniker",
        [
            ("https://github.com/acme/widgets.git", "repo:github.com:acme/widgets"),
            ("https://github.com/acme/widgets", "repo:github.com:acme/widgets"),
            (
                "http://gitlab.example.com/acme/widgets",
                "repo:gitlab.example.com:acme/widgets",
            ),
            ("git@github.com:acme/widgets.git", "repo:github.com:acme/widgets"),
            ("ssh://git@github.com/acme/widgets.git", "repo:github.com:acme/widgets"),
            ("git://github.com/acme/widgets.git", "repo:github.com:acme/widgets"),
            ("https://gitlab.com/group/sub/proj.git", "repo:gitlab.com:sub/proj"),
        ],
    )
    def test_parses_remote_forms(self, origin: str, moniker: str) -> None:
        """HTTPS, SSH, scp-style and git remotes all yield a repository moniker."""
        parsed, _ = parse_origin_url(origin)
        assert str(parsed) == moniker

    @pytest.mark.parametrize(
        "origin",
        [
            "/srv/repos/acme/widgets",
            "C:\\repos\\acme\\widgets",
            "file:///srv/repos/acme/widgets",
            "../repos/acme/widgets".replace("..", "sub"),
        ],
    )
    def test_local_paths_use_the_local_host(self, origin: str) -> None:
        """A repository ingested from disk still has a well-formed moniker.

        Without this, a locally ingested repository could not be joined against like
        any other, and every cross-repository query would have to special-case it.
        """
        moniker, _ = parse_origin_url(origin)
        assert moniker.package == "local"
        assert moniker.descriptor == "acme/widgets"

    def test_strips_embedded_credentials(self) -> None:
        """A token in the URL never reaches the entity.

        PRD section 4.2 keeps facts free of secrets. A credential persisted as a
        fact would leak into every log line and API response that echoes the origin.
        """
        moniker, sanitised = parse_origin_url(
            "https://user:ghp_secrettoken@github.com/acme/widgets.git"
        )
        assert "ghp_secrettoken" not in sanitised
        assert "user" not in sanitised
        assert sanitised == "https://github.com/acme/widgets.git"
        assert str(moniker) == "repo:github.com:acme/widgets"

    def test_preserves_a_non_default_port(self) -> None:
        """A self-hosted forge on a custom port remains reachable."""
        _, sanitised = parse_origin_url("https://git.example.com:8443/acme/widgets.git")
        assert sanitised == "https://git.example.com:8443/acme/widgets.git"

    def test_preserves_the_scp_user(self) -> None:
        """The ssh user is part of the remote, not a credential to strip."""
        _, sanitised = parse_origin_url("git@github.com:acme/widgets.git")
        assert sanitised == "git@github.com:acme/widgets.git"

    @pytest.mark.parametrize("origin", ["", "   ", None])
    def test_rejects_an_empty_origin(self, origin: object) -> None:
        """An empty origin identifies nothing."""
        with pytest.raises(ApplicationError):
            parse_origin_url(origin)  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "origin", ["https://github.com/widgets", "https://github.com/", "widgets"]
    )
    def test_rejects_an_origin_without_owner_and_name(self, origin: str) -> None:
        """A moniker needs both an owner and a name to be unambiguous."""
        with pytest.raises(ApplicationError, match="owner and a repository name"):
            parse_origin_url(origin)

    def test_rejects_an_unsupported_scheme(self) -> None:
        """An unrecognised scheme is refused rather than guessed at."""
        with pytest.raises(ApplicationError, match="scheme is not supported"):
            parse_origin_url("ftp://example.com/acme/widgets")


class TestRegistration:
    """Behaviour of :meth:`RepositoryManager.register`."""

    def test_registers_a_repository(
        self, manager: RepositoryManager, clock: FrozenClock
    ) -> None:
        """Registration records intent to index, with no network access."""
        repository = manager.register(RegisterRepositoryCommand(origin_url=ORIGIN))
        assert repository.status is RepositoryStatus.REGISTERED
        assert repository.slug == "acme/widgets"
        assert repository.registered_at == clock.now()
        assert repository.tenant_id == "default"

    def test_applies_the_default_tenant(self, manager: RepositoryManager) -> None:
        """Tenancy is assigned from configuration when the caller omits it."""
        repository = manager.register(RegisterRepositoryCommand(origin_url=ORIGIN))
        assert repository.tenant_id == "default"

    def test_honours_an_explicit_tenant(self, manager: RepositoryManager) -> None:
        """A caller may place the repository in a specific tenant."""
        repository = manager.register(
            RegisterRepositoryCommand(origin_url=ORIGIN, tenant_id="tenant-b")
        )
        assert repository.tenant_id == "tenant-b"

    def test_records_a_provisional_default_branch(
        self, manager: RepositoryManager
    ) -> None:
        """The default branch is provisional until branch discovery corrects it.

        Probing the remote here would make registration fail when a network is
        briefly unavailable, so acquisition is deferred to Milestone 2.
        """
        repository = manager.register(RegisterRepositoryCommand(origin_url=ORIGIN))
        assert repository.default_branch == "main"

    def test_honours_an_explicit_default_branch(
        self, manager: RepositoryManager
    ) -> None:
        """A caller who knows the branch may supply it."""
        repository = manager.register(
            RegisterRepositoryCommand(origin_url=ORIGIN, default_branch="trunk")
        )
        assert repository.default_branch == "trunk"

    def test_applies_a_supplied_index_policy(self, manager: RepositoryManager) -> None:
        """Configuration is captured at registration."""
        policy = IndexPolicy(feature_branch_cadence=BranchCadence.NEVER)
        repository = manager.register(
            RegisterRepositoryCommand(origin_url=ORIGIN, index_policy=policy)
        )
        assert repository.index_policy.feature_branch_cadence is BranchCadence.NEVER

    def test_rejects_a_duplicate_moniker(self, manager: RepositoryManager) -> None:
        """A second registration raises rather than returning the existing record.

        The two outcomes mean different things to a caller. Silently returning the
        existing repository would hide a conflict in which two callers believe they
        own the same record with different policies.
        """
        manager.register(RegisterRepositoryCommand(origin_url=ORIGIN))
        with pytest.raises(RepositoryAlreadyExistsError) as caught:
            manager.register(
                RegisterRepositoryCommand(origin_url="git@github.com:acme/widgets.git")
            )
        assert "existing_repository_id" in caught.value.context

    def test_a_rejected_registration_leaves_no_trace(
        self, manager: RepositoryManager
    ) -> None:
        """A conflicting registration writes nothing."""
        manager.register(RegisterRepositoryCommand(origin_url=ORIGIN))
        with pytest.raises(RepositoryAlreadyExistsError):
            manager.register(RegisterRepositoryCommand(origin_url=ORIGIN))
        assert manager.count() == 1

    def test_distinct_forges_are_distinct_repositories(
        self, manager: RepositoryManager
    ) -> None:
        """The same owner and name on two hosts are two repositories."""
        manager.register(RegisterRepositoryCommand(origin_url=ORIGIN))
        manager.register(
            RegisterRepositoryCommand(origin_url="https://gitlab.com/acme/widgets.git")
        )
        assert manager.count() == 2

    def test_records_metrics(
        self, manager: RepositoryManager, metrics: InMemoryMetricsSink
    ) -> None:
        """Registration is counted and timed."""
        manager.register(RegisterRepositoryCommand(origin_url=ORIGIN))
        assert (
            metrics.counter_value(
                "ria_repository_registered_total", {"outcome": "registered"}
            )
            == 1
        )
        assert (
            metrics.distribution(
                "ria_repository_operation_seconds",
                {"operation": "register", "outcome": "success"},
            )
            is not None
        )

    def test_counts_a_conflict_separately(
        self, manager: RepositoryManager, metrics: InMemoryMetricsSink
    ) -> None:
        """A conflict is observable as its own outcome, not as a success."""
        manager.register(RegisterRepositoryCommand(origin_url=ORIGIN))
        with pytest.raises(RepositoryAlreadyExistsError):
            manager.register(RegisterRepositoryCommand(origin_url=ORIGIN))
        assert (
            metrics.counter_value(
                "ria_repository_registered_total", {"outcome": "conflict"}
            )
            == 1
        )


class TestReads:
    """Loading repositories."""

    def test_get_by_identifier(self, manager: RepositoryManager) -> None:
        """A registered repository is retrievable by identifier."""
        registered = manager.register(RegisterRepositoryCommand(origin_url=ORIGIN))
        assert manager.get(registered.repository_id) == registered

    def test_get_raises_for_an_unknown_identifier(
        self, manager: RepositoryManager
    ) -> None:
        """An unknown identifier raises with context."""
        with pytest.raises(RepositoryNotFoundError):
            manager.get(RepositoryId.generate())

    def test_get_by_moniker(self, manager: RepositoryManager) -> None:
        """A repository is retrievable by its logical identity."""
        registered = manager.register(RegisterRepositoryCommand(origin_url=ORIGIN))
        assert manager.get_by_moniker(registered.moniker) == registered

    def test_get_by_moniker_raises_when_absent(
        self, manager: RepositoryManager
    ) -> None:
        """An unregistered moniker raises."""
        with pytest.raises(RepositoryNotFoundError):
            manager.get_by_moniker(
                Moniker.for_repository(host="github.com", owner="x", name="y")
            )

    def test_find_returns_none_when_absent(self, manager: RepositoryManager) -> None:
        """Existence checks are ordinary control flow, not exception handling."""
        assert (
            manager.find_by_moniker(
                Moniker.for_repository(host="github.com", owner="x", name="y")
            )
            is None
        )

    def test_list_is_ordered_by_moniker(self, manager: RepositoryManager) -> None:
        """Ordering is deterministic so pagination is stable and caching is sound."""
        for owner in ("zeta", "alpha", "middle"):
            manager.register(
                RegisterRepositoryCommand(
                    origin_url=f"https://github.com/{owner}/widgets.git"
                )
            )
        assert [repository.owner for repository in manager.list()] == [
            "alpha",
            "middle",
            "zeta",
        ]

    def test_list_filters_by_tenant(self, manager: RepositoryManager) -> None:
        """Tenant scoping is applied at the store, not by the caller."""
        manager.register(
            RegisterRepositoryCommand(origin_url=ORIGIN, tenant_id="tenant-a")
        )
        manager.register(
            RegisterRepositoryCommand(
                origin_url="https://github.com/acme/gadgets.git", tenant_id="tenant-b"
            )
        )
        assert len(manager.list(tenant_id="tenant-a")) == 1
        assert manager.count(tenant_id="tenant-b") == 1

    def test_list_filters_by_status(self, manager: RepositoryManager) -> None:
        """Work selection by lifecycle state is supported."""
        first = manager.register(RegisterRepositoryCommand(origin_url=ORIGIN))
        manager.register(
            RegisterRepositoryCommand(origin_url="https://github.com/acme/gadgets.git")
        )
        manager.transition(first.repository_id, RepositoryStatus.INDEXING)
        assert len(manager.list(status=RepositoryStatus.INDEXING)) == 1
        assert len(manager.list(status=RepositoryStatus.REGISTERED)) == 1

    def test_list_paginates(self, manager: RepositoryManager) -> None:
        """Limit and offset produce a stable window over the ordered result."""
        for owner in ("a", "b", "c"):
            manager.register(
                RegisterRepositoryCommand(
                    origin_url=f"https://github.com/{owner}/widgets.git"
                )
            )
        page = manager.list(limit=1, offset=1)
        assert [repository.owner for repository in page] == ["b"]


class TestConfiguration:
    """Reconfiguration and metadata capture."""

    def test_updates_the_index_policy(
        self, manager: RepositoryManager, clock: FrozenClock
    ) -> None:
        """A replaced policy is persisted and timestamped."""
        registered = manager.register(RegisterRepositoryCommand(origin_url=ORIGIN))
        clock.advance(60)
        updated = manager.update_index_policy(
            registered.repository_id,
            IndexPolicy(default_branch_cadence=BranchCadence.MERGE_ONLY),
        )
        assert updated.index_policy.default_branch_cadence is BranchCadence.MERGE_ONLY
        assert updated.updated_at == clock.now()
        assert (
            manager.get(registered.repository_id).index_policy == updated.index_policy
        )

    def test_updates_only_the_supplied_metadata(
        self, manager: RepositoryManager
    ) -> None:
        """Omitted arguments leave their fields untouched."""
        registered = manager.register(RegisterRepositoryCommand(origin_url=ORIGIN))
        updated = manager.update_metadata(
            registered.repository_id, default_branch="trunk"
        )
        assert updated.default_branch == "trunk"
        assert updated.languages == ()

    def test_records_measured_languages_and_size(
        self, manager: RepositoryManager
    ) -> None:
        """Measurements from later milestones land through one entry point."""
        registered = manager.register(RegisterRepositoryCommand(origin_url=ORIGIN))
        profile = LanguageProfile(
            language="python", loc=900, percentage=90.0, tier=LanguageTier.NONE
        )
        updated = manager.update_metadata(
            registered.repository_id,
            languages=(profile,),
            frameworks=("fastapi",),
            size_metrics=SizeMetrics(files=42, loc=1000),
        )
        assert updated.language_by_name()["python"].loc == 900
        assert updated.frameworks == ("fastapi",)
        assert updated.size_metrics.files == 42

    def test_update_raises_for_an_unknown_repository(
        self, manager: RepositoryManager
    ) -> None:
        """Reconfiguring an unregistered repository raises."""
        with pytest.raises(RepositoryNotFoundError):
            manager.update_index_policy(RepositoryId.generate(), IndexPolicy())


class TestLifecycle:
    """State transitions and the purge guard."""

    def test_transitions_through_the_lifecycle(
        self, manager: RepositoryManager
    ) -> None:
        """Registration to active proceeds through the declared states."""
        registered = manager.register(RegisterRepositoryCommand(origin_url=ORIGIN))
        indexing = manager.transition(
            registered.repository_id, RepositoryStatus.INDEXING
        )
        assert indexing.status is RepositoryStatus.INDEXING
        active = manager.record_successful_index(registered.repository_id, sha="a" * 40)
        assert active.status is RepositoryStatus.ACTIVE
        assert active.last_indexed_sha == "a" * 40

    def test_rejects_an_illegal_transition(self, manager: RepositoryManager) -> None:
        """An undeclared transition raises and writes nothing."""
        registered = manager.register(RegisterRepositoryCommand(origin_url=ORIGIN))
        manager.archive(registered.repository_id)
        with pytest.raises(IllegalStateTransitionError):
            manager.transition(registered.repository_id, RepositoryStatus.ACTIVE)
        assert manager.get(registered.repository_id).status is RepositoryStatus.ARCHIVED

    def test_degrading_requires_and_records_a_reason(
        self, manager: RepositoryManager
    ) -> None:
        """Degradation states its cause."""
        registered = manager.register(RegisterRepositoryCommand(origin_url=ORIGIN))
        manager.transition(registered.repository_id, RepositoryStatus.INDEXING)
        degraded = manager.transition(
            registered.repository_id,
            RepositoryStatus.DEGRADED,
            degraded_reason="clone timed out",
        )
        assert degraded.degraded_reason == "clone timed out"

    def test_degrading_without_a_reason_is_rejected(
        self, manager: RepositoryManager
    ) -> None:
        """Silent degradation is impossible, per PRD principle P11."""
        registered = manager.register(RegisterRepositoryCommand(origin_url=ORIGIN))
        manager.transition(registered.repository_id, RepositoryStatus.INDEXING)
        with pytest.raises(ValueError):
            manager.transition(registered.repository_id, RepositoryStatus.DEGRADED)

    def test_purge_requires_prior_archival(self, manager: RepositoryManager) -> None:
        """A purge is always a second, deliberate act.

        Requiring archival first means an irreversible deletion cannot happen
        through a single mistaken call.
        """
        registered = manager.register(RegisterRepositoryCommand(origin_url=ORIGIN))
        with pytest.raises(ApplicationError, match="must be archived"):
            manager.purge(registered.repository_id)
        assert manager.count() == 1

    def test_purge_removes_an_archived_repository(
        self, manager: RepositoryManager
    ) -> None:
        """An archived repository can be purged."""
        registered = manager.register(RegisterRepositoryCommand(origin_url=ORIGIN))
        manager.archive(registered.repository_id)
        assert manager.purge(registered.repository_id) is True
        assert manager.count() == 0

    def test_purge_raises_for_an_unknown_repository(
        self, manager: RepositoryManager
    ) -> None:
        """Purging something unregistered raises rather than reporting success."""
        with pytest.raises(RepositoryNotFoundError):
            manager.purge(RepositoryId.generate())

    def test_state_changes_are_counted(
        self, manager: RepositoryManager, metrics: InMemoryMetricsSink
    ) -> None:
        """Lifecycle movement is observable per target state."""
        registered = manager.register(RegisterRepositoryCommand(origin_url=ORIGIN))
        manager.transition(registered.repository_id, RepositoryStatus.INDEXING)
        assert (
            metrics.counter_value(
                "ria_repository_state_change_total", {"status": "indexing"}
            )
            == 1
        )


class TestTransactionUsage:
    """Transaction discipline of the use cases."""

    def test_every_write_commits_exactly_one_scope(
        self,
        manager: RepositoryManager,
        unit_of_work_factory: InMemoryUnitOfWorkFactory,
    ) -> None:
        """A write opens one transaction and commits it."""
        manager.register(RegisterRepositoryCommand(origin_url=ORIGIN))
        assert len(unit_of_work_factory.scopes) == 1
        assert unit_of_work_factory.scopes[0].was_committed is True

    def test_reads_do_not_commit(
        self,
        manager: RepositoryManager,
        unit_of_work_factory: InMemoryUnitOfWorkFactory,
    ) -> None:
        """A read opens a scope and abandons it, leaving nothing to publish."""
        manager.count()
        assert unit_of_work_factory.scopes[-1].was_committed is False

    def test_read_modify_write_happens_in_one_scope(
        self,
        manager: RepositoryManager,
        unit_of_work_factory: InMemoryUnitOfWorkFactory,
    ) -> None:
        """Mutation loads and saves inside a single transaction.

        Two scopes would let concurrent updates each apply to a stale copy and
        silently lose one another's change.
        """
        registered = manager.register(RegisterRepositoryCommand(origin_url=ORIGIN))
        before = len(unit_of_work_factory.scopes)
        manager.transition(registered.repository_id, RepositoryStatus.INDEXING)
        assert len(unit_of_work_factory.scopes) == before + 1
