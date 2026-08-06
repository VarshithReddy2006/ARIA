"""Conformance of every test double to the port it stands in for.

This module exists because of a real failure. When ``jobs`` was added to
:class:`~ria.ports.unit_of_work.UnitOfWork` in Milestone 2, the in-memory double
silently stopped satisfying the port. Nothing caught it: no test asserted the fake
against the interface, so the divergence would have surfaced as an ``AttributeError``
inside the first unit test written against it, at which point the obvious conclusion
would have been that the new test was wrong.

A double that has drifted from its port is worse than no double. It lets a unit test
pass on behaviour the real adapter does not have, which is the one thing a test must
never do.
"""

from __future__ import annotations

import pytest

from ria.ports.blob_store import ContentAddressableStore
from ria.ports.clock import Clock
from ria.ports.git_client import GitClient
from ria.ports.job_store import JobStore
from ria.ports.metrics import MetricsSink
from ria.ports.progress import ProgressSink
from ria.ports.repositories import (
    BranchStore,
    CommitStore,
    FileUnitStore,
    RepositoryStore,
)
from ria.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from tests.ria.fakes import FakeGitClient, FrozenClock, InMemoryUnitOfWorkFactory


class TestDoubleConformance:
    """Every fake satisfies its port."""

    def test_frozen_clock_is_a_clock(self) -> None:
        """The deterministic clock stands in for the system clock."""
        assert isinstance(FrozenClock(), Clock)

    def test_fake_git_client_is_a_git_client(self) -> None:
        """The scripted git client implements the whole read surface."""
        assert isinstance(FakeGitClient(), GitClient)

    def test_factory_is_a_unit_of_work_factory(self) -> None:
        """The in-memory factory stands in for the SQLite one."""
        assert isinstance(InMemoryUnitOfWorkFactory(), UnitOfWorkFactory)

    def test_unit_of_work_exposes_every_store(self) -> None:
        """The scope satisfies the port, including stores added in later milestones.

        This is the assertion that was missing when ``jobs`` was introduced.
        """
        with InMemoryUnitOfWorkFactory()() as unit_of_work:
            assert isinstance(unit_of_work, UnitOfWork)

    @pytest.mark.parametrize(
        "attribute,port",
        [
            ("repositories", RepositoryStore),
            ("commits", CommitStore),
            ("branches", BranchStore),
            ("file_units", FileUnitStore),
            ("jobs", JobStore),
        ],
    )
    def test_each_store_satisfies_its_port(self, attribute: str, port: type) -> None:
        """Each store behind the scope conforms individually.

        Checked per store rather than only through the scope, so a failure names the
        store that drifted instead of reporting that the whole unit of work is wrong.
        """
        with InMemoryUnitOfWorkFactory()() as unit_of_work:
            assert isinstance(getattr(unit_of_work, attribute), port)


class TestAdapterConformance:
    """Every shipped adapter satisfies its port.

    Duplicated across the unit and integration suites on purpose: the integration
    tests assert conformance on adapters they construct with real dependencies, and
    these assert it on the ones that need none. A port gains a method in one milestone
    and an adapter is forgotten in the next, so the check belongs wherever an
    implementation can be built cheaply.
    """

    def test_progress_sinks_conform(self) -> None:
        """All four progress sinks are interchangeable."""
        from ria.observability.progress import (
            CompositeProgressSink,
            InMemoryProgressSink,
            LoggingProgressSink,
            NullProgressSink,
        )

        for sink in (
            LoggingProgressSink(),
            InMemoryProgressSink(),
            NullProgressSink(),
            CompositeProgressSink(NullProgressSink()),
        ):
            assert isinstance(sink, ProgressSink), type(sink).__name__

    def test_metrics_sinks_conform(self) -> None:
        """Both metrics sinks are interchangeable, so disabling metrics is a swap."""
        from ria.observability.metrics import InMemoryMetricsSink, NullMetricsSink

        assert isinstance(InMemoryMetricsSink(), MetricsSink)
        assert isinstance(NullMetricsSink(), MetricsSink)

    def test_system_clock_conforms(self) -> None:
        """The production clock satisfies the same port as the test double."""
        from ria.infrastructure.system_clock import SystemClock

        assert isinstance(SystemClock(), Clock)

    def test_blob_store_conforms(self, tmp_path) -> None:
        """The filesystem store satisfies the content-addressable port."""
        from ria.infrastructure.storage.filesystem_blob_store import FilesystemBlobStore
        from ria.observability.metrics import NullMetricsSink

        store = FilesystemBlobStore(tmp_path / "blobs", NullMetricsSink())
        assert isinstance(store, ContentAddressableStore)

    def test_git_client_conforms(self) -> None:
        """The subprocess adapter satisfies the git port without invoking git."""
        from ria.config.settings import GitSettings
        from ria.infrastructure.git.subprocess_git_client import SubprocessGitClient
        from ria.observability.metrics import NullMetricsSink

        assert isinstance(
            SubprocessGitClient(GitSettings(), NullMetricsSink()), GitClient
        )
