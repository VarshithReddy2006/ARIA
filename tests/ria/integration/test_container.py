"""Integration tests for the composition root and an end-to-end Milestone 1 flow.

Two things are verified here that no narrower test can reach: that the graph wires
together and satisfies its ports, and that the milestone's use cases compose into a
working sequence against real adapters — register, discover branches, resolve a ref,
record a commit, read it back.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ria.application.repository_manager import RegisterRepositoryCommand
from ria.config.settings import Settings, StorageSettings
from ria.container import Container, build_container
from ria.domain.enums import CommitIndexState, RepositoryStatus
from ria.domain.errors import ConfigurationError
from ria.domain.identity import ContentHash, Moniker
from ria.domain.language import DEFAULT_LANGUAGE_CATALOGUE, LanguageCatalogue
from ria.ports.blob_store import ContentAddressableStore
from ria.ports.clock import Clock
from ria.ports.git_client import GitClient
from ria.ports.metrics import MetricsSink
from ria.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from tests.ria.conftest import commit_files, head_sha, requires_git, run_git


class TestWiring:
    """Construction of the application graph."""

    def test_every_member_satisfies_its_port(self, container: Container) -> None:
        """Adapters conform structurally to the interfaces they are wired to.

        Checked at the composition root because this is the only place where the
        choice of adapter is made, and a mismatch here would surface as an
        ``AttributeError`` deep inside a use case.
        """
        assert isinstance(container.clock, Clock)
        assert isinstance(container.metrics, MetricsSink)
        assert isinstance(container.git, GitClient)
        assert isinstance(container.blob_store, ContentAddressableStore)
        assert isinstance(container.unit_of_work_factory, UnitOfWorkFactory)
        with container.unit_of_work_factory() as unit_of_work:
            assert isinstance(unit_of_work, UnitOfWork)

    def test_is_immutable(self, container: Container) -> None:
        """The graph is built once and cannot be swapped afterwards.

        A container whose members could be replaced would reintroduce the ambient
        mutable state this design exists to avoid.
        """
        import dataclasses

        with pytest.raises(dataclasses.FrozenInstanceError):
            container.metrics = None  # type: ignore[misc]

    def test_migrations_run_by_default(self, container: Container) -> None:
        """A freshly built container is immediately usable."""
        with container.unit_of_work_factory() as unit_of_work:
            assert unit_of_work.repositories.count() == 0

    def test_migrations_can_be_deferred(self, settings: Settings) -> None:
        """A caller may control migration timing.

        Useful for a deployment that migrates in a separate step, and required for
        any test that wants to observe the unmigrated state.
        """
        built = build_container(settings, run_migrations=False)
        try:
            from ria.infrastructure.storage.sqlite.migrations import MigrationRunner

            assert MigrationRunner(built.connections).current_version() == 0
        finally:
            built.close()

    def test_creates_every_required_directory(self, settings: Settings) -> None:
        """Directories are created once at startup, not lazily at first use.

        Lazy creation would race between workers and produce intermittent failures.
        """
        built = build_container(settings)
        try:
            assert settings.storage.data_root.is_dir()
            assert settings.storage.blob_store_path.is_dir()
            assert settings.storage.mirror_root.is_dir()
            assert settings.storage.database_path.parent.is_dir()
        finally:
            built.close()

    def test_two_containers_coexist(self, tmp_path: Path) -> None:
        """Independent graphs do not interfere.

        Import has no side effects and construction is explicit, so one process can
        serve two configurations — which is what makes tests isolated.
        """
        first = build_container(Settings.for_testing(tmp_path / "one"))
        second = build_container(Settings.for_testing(tmp_path / "two"))
        try:
            first.repository_manager.register(
                RegisterRepositoryCommand(origin_url="https://github.com/a/b.git")
            )
            assert first.repository_manager.count() == 1
            assert second.repository_manager.count() == 0
        finally:
            first.close()
            second.close()

    def test_language_catalogue_is_overridable(self, settings: Settings) -> None:
        """A caller may substitute the classification table."""
        catalogue = LanguageCatalogue(())
        built = build_container(settings, language_catalogue=catalogue)
        try:
            assert built.language_catalogue is catalogue
        finally:
            built.close()

    def test_defaults_to_the_shipped_catalogue(self, container: Container) -> None:
        """Without an override, the shipped table is used."""
        assert container.language_catalogue is DEFAULT_LANGUAGE_CATALOGUE

    def test_metrics_sink_follows_configuration(self, tmp_path: Path) -> None:
        """Disabling metrics substitutes a sink rather than adding conditionals."""
        from ria.config.settings import ObservabilitySettings
        from ria.observability.metrics import InMemoryMetricsSink, NullMetricsSink

        enabled = build_container(Settings.for_testing(tmp_path / "on"))
        disabled = build_container(
            Settings(
                environment="test",
                storage=StorageSettings(data_root=tmp_path / "off"),
                observability=ObservabilitySettings(metrics_enabled=False),
            )
        )
        try:
            assert isinstance(enabled.metrics, InMemoryMetricsSink)
            assert isinstance(disabled.metrics, NullMetricsSink)
        finally:
            enabled.close()
            disabled.close()

    def test_close_is_idempotent(self, settings: Settings) -> None:
        """Closing twice is safe, so teardown paths need no guard."""
        built = build_container(settings)
        built.close()
        built.close()


class TestMirrorPathDerivation:
    """Resolution of a repository's local mirror directory."""

    def test_derives_a_path_under_the_mirror_root(self, container: Container) -> None:
        """The mapping is derived, not stored, so it cannot drift."""
        moniker = Moniker.for_repository(
            host="github.com", owner="acme", name="widgets"
        )
        path = container.mirror_path(moniker)
        assert path.parent == container.settings.storage.mirror_root

    def test_is_deterministic(self, container: Container) -> None:
        """The same moniker always resolves to the same directory."""
        moniker = Moniker.for_repository(
            host="github.com", owner="acme", name="widgets"
        )
        assert container.mirror_path(moniker) == container.mirror_path(str(moniker))

    def test_distinct_repositories_get_distinct_directories(
        self, container: Container
    ) -> None:
        """Two repositories never share a mirror."""
        first = Moniker.for_repository(host="github.com", owner="acme", name="widgets")
        second = Moniker.for_repository(host="gitlab.com", owner="acme", name="widgets")
        assert container.mirror_path(first) != container.mirror_path(second)

    @pytest.mark.parametrize(
        "descriptor",
        ["../../etc", "a/../../b", "a\\b", "a:b"],
    )
    def test_a_hostile_moniker_cannot_escape_the_root(
        self, container: Container, descriptor: str
    ) -> None:
        """Sanitisation keeps the mirror confined regardless of the moniker.

        A moniker derives from a remote URL, which is caller-supplied, so path
        containment must be enforced rather than assumed.
        """
        path = container.mirror_path(f"repo:host:{descriptor}")
        root = container.settings.storage.mirror_root
        assert path.parent == root
        assert root in path.parents


class TestSettings:
    """Configuration resolution."""

    def test_paths_are_absolute(self, settings: Settings) -> None:
        """Every path is resolved at construction.

        A later change of working directory cannot silently relocate the facts
        store.
        """
        assert settings.storage.database_path.is_absolute()
        assert settings.storage.blob_store_path.is_absolute()
        assert settings.storage.mirror_root.is_absolute()

    def test_derives_paths_from_the_data_root(self, tmp_path: Path) -> None:
        """Unset paths default to a location under the data root."""
        storage = StorageSettings(data_root=tmp_path / "root")
        assert storage.database_path.parent == (tmp_path / "root").resolve()
        assert storage.blob_store_path.name == "blobs"
        assert storage.mirror_root.name == "mirrors"

    def test_honours_explicit_paths(self, tmp_path: Path) -> None:
        """An explicit path overrides the derived one."""
        explicit = tmp_path / "elsewhere" / "facts.db"
        storage = StorageSettings(data_root=tmp_path / "root", database_path=explicit)
        assert storage.database_path == explicit.resolve()

    def test_database_is_separate_from_the_legacy_store(
        self, settings: Settings
    ) -> None:
        """The two migration chains cannot interleave."""
        assert settings.storage.database_path.name == "ria.db"

    def test_test_settings_are_marked_as_such(self, settings: Settings) -> None:
        """A test configuration is identifiable and not production."""
        assert settings.environment == "test"
        assert settings.is_production is False

    def test_log_level_accepts_lowercase(self) -> None:
        """A lowercase level from the environment is normalised."""
        from ria.config.settings import ObservabilitySettings

        assert ObservabilitySettings(log_level="debug").log_level == "DEBUG"

    def test_reports_an_uncreatable_directory(self, tmp_path: Path) -> None:
        """A directory that cannot be created is a configuration fault.

        Reported as such rather than surfacing later as an obscure write failure.
        """
        blocker = tmp_path / "blocked"
        blocker.write_text("not a directory", encoding="utf-8")
        settings = Settings(
            environment="test", storage=StorageSettings(data_root=blocker / "data")
        )
        with pytest.raises(ConfigurationError):
            settings.ensure_directories()


class TestEndToEndFlow:
    """The Milestone 1 sequence against real adapters."""

    @requires_git
    def test_register_discover_resolve_and_record(
        self, container: Container, make_git_repo
    ) -> None:
        """A repository is registered, its branches and a commit are recorded.

        This is the full extent of Milestone 1: ingestion of file content and
        manifests is Milestone 2, so the flow stops at commit facts.
        """
        repository_path = make_git_repo(
            files={"README.md": "# fixture\n", "src/a.py": "a = 1\n"}
        )
        run_git(repository_path, "branch", "feature/x")

        registered = container.repository_manager.register(
            RegisterRepositoryCommand(origin_url=str(repository_path))
        )
        assert registered.status is RepositoryStatus.REGISTERED

        recorded_branches = container.commit_resolver.record_branches(
            registered.repository_id, repository_path
        )
        assert recorded_branches == 2

        outcome = container.commit_resolver.resolve_and_record(
            registered.repository_id, repository_path, "main"
        )
        assert outcome.was_already_recorded is False
        assert outcome.sha.value == head_sha(repository_path)
        assert outcome.commit.index_state is CommitIndexState.DISCOVERED

        reloaded = container.commit_resolver.get(registered.repository_id, outcome.sha)
        assert reloaded.author.email == "ada@example.com"
        assert reloaded.subject == "initial commit"

    @requires_git
    def test_the_default_branch_is_corrected_from_observation(
        self, container: Container, make_git_repo
    ) -> None:
        """Registration records a provisional branch; discovery corrects it.

        Registration performs no network access, so the observed value can only
        arrive later — which is why the field is updatable rather than fixed.
        """
        repository_path = make_git_repo(default_branch="trunk")
        registered = container.repository_manager.register(
            RegisterRepositoryCommand(origin_url=str(repository_path))
        )
        assert registered.default_branch == "main"

        observed = container.git.detect_default_branch(repository_path)
        updated = container.repository_manager.update_metadata(
            registered.repository_id, default_branch=observed
        )
        assert updated.default_branch == "trunk"

    @requires_git
    def test_repeated_recording_is_idempotent(
        self, container: Container, make_git_repo
    ) -> None:
        """Re-running the sequence writes nothing further and cannot fail."""
        repository_path = make_git_repo()
        registered = container.repository_manager.register(
            RegisterRepositoryCommand(origin_url=str(repository_path))
        )
        for _ in range(3):
            container.commit_resolver.record_branches(
                registered.repository_id, repository_path
            )
            container.commit_resolver.resolve_and_record(
                registered.repository_id, repository_path, "main"
            )
        with container.unit_of_work_factory() as unit_of_work:
            counts = unit_of_work.commits.count_by_state(registered.repository_id)
            branches = unit_of_work.branches.list(registered.repository_id)
        assert counts == {"discovered": 1}
        assert len(branches) == 1

    @requires_git
    def test_history_is_walkable_and_commit_scoped(
        self, container: Container, make_git_repo
    ) -> None:
        """Each commit is recorded independently and keyed to itself.

        Twin Spec section 3.1 Rule 2 requires every fact to be commit-keyed; two
        commits of one repository must therefore be two distinct records.
        """
        repository_path = make_git_repo()
        first = head_sha(repository_path)
        second = commit_files(repository_path, {"src/a.py": "a = 1\n"}, "second")

        registered = container.repository_manager.register(
            RegisterRepositoryCommand(origin_url=str(repository_path))
        )
        for ref in (first, second):
            container.commit_resolver.resolve_and_record(
                registered.repository_id, repository_path, ref
            )
        with container.unit_of_work_factory() as unit_of_work:
            counts = unit_of_work.commits.count_by_state(registered.repository_id)
        assert counts == {"discovered": 2}

        recorded = container.commit_resolver.get(
            registered.repository_id,
            container.commit_resolver.resolve(repository_path, second).sha,
        )
        assert recorded.parents[0].value == first

    @requires_git
    def test_blob_content_is_addressable_from_a_real_repository(
        self, container: Container, make_git_repo
    ) -> None:
        """Content read from git is storable and retrievable by its digest.

        This is the pairing Milestone 2 depends on: git supplies bytes, the store
        supplies identity, and the identity is what makes parse reuse possible.
        """
        payload = "def handler():\n    return 200\n"
        repository_path = make_git_repo(files={"src/a.py": payload})
        entry = container.git.list_tree(repository_path, head_sha(repository_path))[0]
        content = container.git.read_blob(repository_path, entry.blob_sha)

        stored = container.blob_store.put(content)
        assert stored == ContentHash.of_bytes(payload.encode())
        assert container.blob_store.get(stored) == payload.encode()
        assert container.git.count_lines(content) == 2

    @requires_git
    def test_purge_removes_the_repository_and_its_commits(
        self, container: Container, make_git_repo
    ) -> None:
        """The archive-then-purge sequence removes every owned fact."""
        repository_path = make_git_repo()
        registered = container.repository_manager.register(
            RegisterRepositoryCommand(origin_url=str(repository_path))
        )
        container.commit_resolver.resolve_and_record(
            registered.repository_id, repository_path, "main"
        )
        container.repository_manager.archive(registered.repository_id)
        assert container.repository_manager.purge(registered.repository_id) is True
        with container.unit_of_work_factory() as unit_of_work:
            assert unit_of_work.commits.count_by_state(registered.repository_id) == {}
